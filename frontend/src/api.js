import axios from 'axios'

export const api = axios.create({
  baseURL: '/api',
  timeout: 10000,
  // Cookie 鉴权:7 天 HttpOnly cookie 需浏览器自动带上
  withCredentials: true,
})

export default api
