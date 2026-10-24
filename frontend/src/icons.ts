import { Camera, Landmark, Mail, MessageSquareText, Receipt, Users, type LucideIcon } from "lucide-react";

/** One icon per evidence source, shared by intake, drawer, proof and trace screens. */
export const SOURCE_ICON: Record<string, LucideIcon> = {
  sms: MessageSquareText,
  email: Mail,
  ais: Receipt,
  photo: Camera,
  photos: Camera,
  portal: Landmark,
  family: Users,
};
