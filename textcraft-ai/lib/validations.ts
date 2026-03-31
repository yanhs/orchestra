import { z } from 'zod';

export const processRequestSchema = z.object({
  tool: z.enum(['summarize', 'rewrite', 'seo']),
  text: z.string().min(10, 'Text must be at least 10 characters').max(5000, 'Text must be under 5000 characters'),
  options: z.object({
    length: z.enum(['short', 'medium', 'long']).optional(),
    tone: z.enum(['formal', 'casual', 'persuasive', 'simple']).optional(),
    targetKeyword: z.string().max(100).optional(),
    includeMetaDescription: z.boolean().optional(),
  }).optional(),
  proToken: z.string().optional(),
});

export const checkoutRequestSchema = z.object({
  email: z.string().email().optional(),
});
