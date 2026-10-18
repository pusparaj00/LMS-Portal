export type ItemKind = "text" | "link" | "video" | "file";

export type ContentItem = {
  id: number;
  kind: ItemKind;
  title: string;
  body: string | null;
  url: string | null;
  file_name: string | null;
  file_size: number | null;
  published: boolean;
  completed: boolean | null;
};

export type ContentModule = {
  id: number;
  title: string;
  published: boolean;
  items: ContentItem[];
  total: number;
  completed: number | null;
  completion_rate: number | null;
};

export type Content = { modules: ContentModule[]; total: number; completed: number | null };

export const MAX_PDF_BYTES = 4_500_000;

export const KIND_LABEL: Record<ItemKind, string> = { text: "Text", link: "Link", video: "Video link", file: "PDF" };

export const size = (bytes: number) => (bytes >= 1_000_000 ? `${(bytes / 1_000_000).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1000))} KB`);
