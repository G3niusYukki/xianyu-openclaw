import { api } from './index';
import type { AxiosResponse } from 'axios';

export const getTemplates = (): Promise<AxiosResponse> => api.get('/listing/templates');

export const previewListing = (data: Record<string, any>): Promise<AxiosResponse> =>
  api.post('/listing/preview', data);

export const publishListing = (data: Record<string, any>): Promise<AxiosResponse> =>
  api.post('/listing/publish', data);
