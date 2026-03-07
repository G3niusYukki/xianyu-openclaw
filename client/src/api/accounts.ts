import { api } from './index';
import type { AxiosResponse } from 'axios';

export const getAccounts = (): Promise<AxiosResponse> => api.get('/accounts');
