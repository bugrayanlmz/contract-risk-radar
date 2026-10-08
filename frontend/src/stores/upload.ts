import { create } from "zustand";

type UploadState = {
  file: File | null;
  confirmed: boolean;
  documentKind: "synthetic" | "real";
  setDocumentKind: (documentKind: "synthetic" | "real") => void;
  setFile: (file: File | null) => void;
  setConfirmed: (confirmed: boolean) => void;
  reset: () => void;
};

export const useUploadStore = create<UploadState>((set) => ({
  file: null,
  documentKind: "synthetic",
  setDocumentKind: (documentKind) => set({ documentKind, confirmed: false }),
  confirmed: false,
  setFile: (file) => set({ file, confirmed: false }),
  setConfirmed: (confirmed) => set({ confirmed }),
  reset: () => set({ file: null, confirmed: false, documentKind: "synthetic" }),
}));
