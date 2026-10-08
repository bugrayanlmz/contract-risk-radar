import { queryOptions } from "@tanstack/react-query";
import { client } from "./generated/client.gen";
import {
  getMe,
  getCapabilities,
  getDocument,
  getResults,
  listDocuments,
  listSamples,
} from "./generated/sdk.gen";

client.setConfig({
  baseUrl: "",
  credentials: "same-origin",
  throwOnError: true,
});

export const meQuery = queryOptions({
  queryKey: ["me"],
  queryFn: async () => (await getMe()).data!,
  retry: false,
  staleTime: 60_000,
});
export const documentsQuery = queryOptions({
  queryKey: ["documents"],
  queryFn: async () => (await listDocuments()).data!,
});
export const samplesQuery = queryOptions({
  queryKey: ["samples"],
  queryFn: async () => (await listSamples()).data!,
});
export const documentQuery = (id: string) =>
  queryOptions({
    queryKey: ["document", id],
    queryFn: async () =>
      (await getDocument({ path: { document_id: id } })).data!,
    refetchInterval: (query) =>
      query.state.data?.status === "processing" ? 2000 : false,
  });
export const resultsQuery = (id: string) =>
  queryOptions({
    queryKey: ["results", id],
    queryFn: async () =>
      (await getResults({ path: { document_id: id } })).data!,
  });

export function errorMessage(error: unknown): string {
  if (typeof error === "object" && error && "error" in error) {
    const detail = error.error;
    if (
      typeof detail === "object" &&
      detail &&
      "message" in detail &&
      typeof detail.message === "string"
    )
      return detail.message;
  }
  return error instanceof Error
    ? error.message
    : "The request could not be completed. Please try again.";
}

export const capabilitiesQuery = queryOptions({
  queryKey: ["capabilities"],
  queryFn: async () => (await getCapabilities()).data!,
  staleTime: 60_000,
});
