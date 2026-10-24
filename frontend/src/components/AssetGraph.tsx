import { useCallback, useEffect, useRef, useState } from "react";
import { forceCollide, forceX, forceY } from "d3-force";
import ForceGraph2D, { type ForceGraphMethods, type LinkObject, type NodeObject } from "react-force-graph-2d";
import { useGhostStore, type GhostData } from "../store";
import { formatShort } from "../format";
import type { Asset, Status } from "../types";

// Node and link objects are created once and then mutated in place: force-graph stores positions on
// them, and handing it fresh objects would restart every node from scratch. graphData is only
// replaced when nodes or links are added/removed, at most once per animation frame.

interface GNode {
  id: string;
  kind: "clue" | "asset";
  born: number; // performance.now() when first seen, drives the fade-in
  asset?: Asset;
}
interface GLink {
  id: string;
}
type N = NodeObject<GNode>;
type L = LinkObject<GNode, GLink>;

const FADE_MS = 700;
const FIT_PADDING = 130; // px; zoomToFit only sees node centres, so leave room for big circles + labels
const MAX_ZOOM = 2.2; // stops a handful of early clue dots filling the screen
const CLUE_SCREEN_PX = 3.5;
const CLUE_COLOR = "#a39e8e";
const LINK_COLOR = "rgba(207, 201, 180, 0.22)";
const STATUS_FILL: Record<Status, string> = {
  active: "#FFB54D", // accent orange
  dormant: "#E8B830", // amber
  transferred_dea: "#2F2F2F",
  transferred_iepf: "#2F2F2F",
  transferred_scwf: "#2F2F2F",
  unknown: "#CFC9B4",
};
const TRANSFERRED_STROKE = "#FF5A4E";
const isTransferred = (s: Status) => s.startsWith("transferred");

/** Radius in graph units, growing with value (₹45K ≈ 16, ₹1.2L ≈ 22, ₹4L ≈ 33, ₹15L ≈ 57). */
const assetRadius = (a: Asset) => (a.est_value ? 8 + Math.sqrt(a.est_value) / 25 : 14);
const CLUE_RADIUS = 3;

/** "State Bank of India ··3307" so two accounts at one bank can be told apart. */
const assetLabel = (a: Asset) => {
  const tail = a.identifier?.replace(/\s+/g, "").slice(-4);
  return tail ? `${a.institution} ··${tail}` : a.institution;
};

function useSize<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) =>
      setSize({ width: entry.contentRect.width, height: entry.contentRect.height }),
    );
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, size] as const;
}

export default function AssetGraph({ onAssetClick }: { onAssetClick?: (assetId: string) => void }) {
  const fg = useRef<ForceGraphMethods<N, L> | undefined>(undefined);
  const [box, size] = useSize<HTMLDivElement>();
  const nodes = useRef(new Map<string, N>());
  const links = useRef(new Map<string, L>());
  const [graphData, setGraphData] = useState<{ nodes: N[]; links: L[] }>({ nodes: [], links: [] });
  const lastFit = useRef(0);
  const needsFit = useRef(false);

  // Mirror the store into stable node/link objects.
  const sync = useCallback((s: GhostData) => {
    const now = performance.now();
    let changed = false;
    if (s.eventCount === 0 && nodes.current.size) {
      nodes.current.clear(); // store was reset
      links.current.clear();
      changed = true;
    }

    for (const clue of s.clues) {
      if (!nodes.current.has(clue.id)) {
        nodes.current.set(clue.id, { id: clue.id, kind: "clue", born: now });
        changed = true;
      }
    }

    const wanted = new Set<string>();
    for (const asset of Object.values(s.assets)) {
      const nodeId = `asset:${asset.id}`;
      let node = nodes.current.get(nodeId);
      if (!node) {
        // Start the asset at the centre of its clues so it grows out of them.
        const placed = asset.clue_ids.map((id) => nodes.current.get(id)).filter((n): n is N => n?.x != null);
        node = { id: nodeId, kind: "asset", born: now };
        if (placed.length) {
          node.x = placed.reduce((sum, n) => sum + n.x!, 0) / placed.length;
          node.y = placed.reduce((sum, n) => sum + n.y!, 0) / placed.length;
        }
        nodes.current.set(nodeId, node);
        changed = true;
      }
      node.asset = asset; // status/value updates show up on the next frame

      for (const clueId of asset.clue_ids) {
        if (!nodes.current.has(clueId)) continue;
        const linkId = `${nodeId}>${clueId}`;
        wanted.add(linkId);
        if (!links.current.has(linkId)) {
          links.current.set(linkId, { id: linkId, source: nodeId, target: clueId });
          changed = true;
        }
      }
    }
    for (const linkId of links.current.keys()) {
      if (!wanted.has(linkId)) {
        links.current.delete(linkId); // asset was re-clustered
        changed = true;
      }
    }
    if (changed) {
      needsFit.current = true;
      setGraphData({ nodes: [...nodes.current.values()], links: [...links.current.values()] });
    }
  }, []);

  useEffect(() => {
    let raf = 0;
    const schedule = () => {
      if (raf) return;
      raf = requestAnimationFrame(() => {
        raf = 0;
        sync(useGhostStore.getState());
      });
    };
    schedule();
    const unsubscribe = useGhostStore.subscribe(schedule);
    return () => {
      unsubscribe();
      cancelAnimationFrame(raf);
    };
  }, [sync]);

  // Clues barely repel each other and ring their asset; assets push apart just enough for labels.
  // Kept compact on purpose: zoomToFit then zooms IN, so circles and labels read on a projector.
  useEffect(() => {
    const graph = fg.current;
    if (!graph) return;
    graph.d3Force("charge")?.strength((n: N) => (n.asset ? -60 : -3));
    graph.d3Force("link")?.distance((l: L) => {
      const src = l.source as N;
      return src.asset ? assetRadius(src.asset) + 12 : 30;
    });
    // Gravity (weaker sideways, since the panel is wide) stops outliers stretching the fit;
    // collision leaves room under each asset for its two-line label.
    graph.d3Force("x", forceX<N>(0).strength(0.05));
    graph.d3Force("y", forceY<N>(0).strength(0.12));
    graph.d3Force(
      "collide",
      forceCollide<N>((n) => (n.asset ? assetRadius(n.asset) + 34 : CLUE_RADIUS + 1)).iterations(2),
    );
  }, [size.width > 0]);

  // Refit when the panel resizes (e.g. the final banner pushes the layout down).
  useEffect(() => {
    needsFit.current = true;
    const t = window.setTimeout(() => fg.current?.zoomToFit(600, FIT_PADDING), 50);
    return () => window.clearTimeout(t);
  }, [size.width, size.height]);

  const drawNode = useCallback((node: N, ctx: CanvasRenderingContext2D, scale: number) => {
    const t = Math.min(1, (performance.now() - node.born) / FADE_MS);
    const x = node.x ?? 0;
    const y = node.y ?? 0;
    ctx.globalAlpha = t;

    if (node.kind === "clue" || !node.asset) {
      ctx.fillStyle = CLUE_COLOR;
      ctx.beginPath();
      ctx.arc(x, y, CLUE_SCREEN_PX / scale, 0, 2 * Math.PI); // constant on-screen size
      ctx.fill();
      ctx.globalAlpha = 1;
      return;
    }

    const a = node.asset;
    const r = assetRadius(a) * (0.5 + 0.5 * t);
    ctx.beginPath();
    ctx.arc(x, y, r, 0, 2 * Math.PI);
    ctx.fillStyle = STATUS_FILL[a.status] ?? STATUS_FILL.unknown;
    ctx.fill();
    if (isTransferred(a.status)) {
      ctx.lineWidth = Math.max(2.5, 3 / scale);
      ctx.strokeStyle = TRANSFERRED_STROKE;
      ctx.stroke();
    }

    // Labels keep a constant on-screen size whatever the zoom.
    const font = 15 / scale;
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    ctx.font = `600 ${font}px system-ui, sans-serif`;
    ctx.fillStyle = "#FDF9E0";
    ctx.fillText(assetLabel(a), x, y + r + 4 / scale);
    if (a.est_value != null) {
      ctx.font = `700 ${font}px system-ui, sans-serif`;
      ctx.fillStyle = "#FFB54D";
      ctx.fillText(formatShort(a.est_value), x, y + r + 4 / scale + font * 1.2);
    }
    ctx.globalAlpha = 1;
  }, []);

  // Only asset circles are clickable; clue dots paint no hit area, so hover detection stays cheap.
  const paintHitArea = useCallback((node: N, color: string, ctx: CanvasRenderingContext2D) => {
    if (!node.asset) return;
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(node.x ?? 0, node.y ?? 0, assetRadius(node.asset) + 4, 0, 2 * Math.PI);
    ctx.fill();
  }, []);

  const onTick = useCallback(() => {
    const now = performance.now();
    if (needsFit.current && now - lastFit.current > 1500 && graphData.nodes.length > 1) {
      lastFit.current = now;
      needsFit.current = false;
      fg.current?.zoomToFit(800, FIT_PADDING);
    }
  }, [graphData]);

  return (
    <div ref={box} className="relative h-full w-full overflow-hidden rounded-lg bg-card">
      {size.width > 0 && (
        <ForceGraph2D<GNode, GLink>
          ref={fg}
          width={size.width}
          height={size.height}
          graphData={graphData}
          backgroundColor="#2F2F2F"
          nodeCanvasObject={drawNode}
          linkColor={() => LINK_COLOR}
          linkWidth={0.6}
          maxZoom={MAX_ZOOM}
          nodePointerAreaPaint={paintHitArea}
          showPointerCursor={(obj) => !!(obj && "kind" in obj && obj.kind === "asset")}
          onNodeClick={(node) => node.asset && onAssetClick?.(node.asset.id)}
          enableNodeDrag={false}
          autoPauseRedraw={false}
          cooldownTime={8000}
          d3VelocityDecay={0.35}
          onEngineTick={onTick}
          onEngineStop={() => fg.current?.zoomToFit(800, FIT_PADDING)}
        />
      )}
      <Legend />
    </div>
  );
}

function Legend() {
  const item = (label: string, swatch: React.ReactNode) => (
    <div className="flex items-center gap-2">
      {swatch}
      <span>{label}</span>
    </div>
  );
  const dot = (color: string, extra = "") => (
    <span className={`inline-block h-3.5 w-3.5 rounded-full ${extra}`} style={{ background: color }} />
  );
  return (
    <div className="pointer-events-none absolute bottom-4 left-4 flex gap-5 rounded bg-page/70 px-4 py-2 text-sm text-muted">
      {item("clue", dot(CLUE_COLOR, "!h-2 !w-2"))}
      {item("active", dot(STATUS_FILL.active))}
      {item("dormant", dot(STATUS_FILL.dormant))}
      {item("transferred", <span className="inline-block h-3.5 w-3.5 rounded-full border-2" style={{ borderColor: TRANSFERRED_STROKE }} />)}
      {item("unknown", dot(STATUS_FILL.unknown))}
    </div>
  );
}
