import { pyApi } from './index';

export const getAccounts = () => pyApi.get('/api/accounts');
