import { api } from './index';
import type { AxiosResponse } from 'axios';
import type { ApiResponse } from './index';

export interface ConfigSection {
  key: string;
  name: string;
  fields?: ConfigField[];
}

export interface ConfigField {
  key: string;
  label: string;
  type: string;
  required?: boolean;
  required_when?: Record<string, string>;
  default?: any;
  options?: string[];
  labels?: Record<string, string>;
  hint?: string;
  placeholder?: string;
}

export const getSystemConfig = (): Promise<AxiosResponse<ApiResponse & { config: Record<string, any> }>> =>
  api.get('/config');

export const saveSystemConfig = (updates: Record<string, any>): Promise<AxiosResponse<ApiResponse & { config: Record<string, any> }>> =>
  api.put('/config', updates);

export const getConfigSections = (): Promise<AxiosResponse<ApiResponse & { sections: ConfigSection[] }>> =>
  api.get('/config/sections');
