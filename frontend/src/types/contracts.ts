export type ContractStatus = "PENDING" | "PROCESSED" | "FAILED";

export interface ContractSummary {
  id: number;
  title: string;
  upload_date: string;
  status: ContractStatus;
}

export interface ContractHealthResponse {
  status: string;
}


