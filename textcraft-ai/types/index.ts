export type ToolType = 'summarize' | 'rewrite' | 'seo';

export type SummarizeLength = 'short' | 'medium' | 'long';
export type RewriteTone = 'formal' | 'casual' | 'persuasive' | 'simple';

export interface ToolOptions {
  length?: SummarizeLength;
  tone?: RewriteTone;
  targetKeyword?: string;
  includeMetaDescription?: boolean;
}

export interface ProcessRequest {
  tool: ToolType;
  text: string;
  options?: ToolOptions;
  proToken?: string;
}

export interface ProcessResponse {
  result: string;
  tool: ToolType;
  wordCount: {
    input: number;
    output: number;
  };
  processingMs: number;
}

export interface UsageData {
  count: number;
  date: string;
}

export interface ApiError {
  error: string;
  message: string;
  usedToday?: number;
  resetAt?: string;
}
