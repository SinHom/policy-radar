import axios from 'axios'

export const api = axios.create({
  baseURL: '/api',
  timeout: 10000,
  // Cookie 鉴权:7 天 HttpOnly cookie 需浏览器自动带上
  withCredentials: true,
})

// 401 拦截:任何写操作/读操作返回 401 都跳登录页(避免用户卡在后台但什么都不工作)
let redirecting = false
api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401 && !redirecting && !window.location.pathname.startsWith('/login')) {
      redirecting = true
      const redirect = encodeURIComponent(window.location.pathname + window.location.search)
      window.location.href = `/login?redirect=${redirect}`
      // 防止后续多个 401 重复跳转
      setTimeout(() => { redirecting = false }, 2000)
    }
    return Promise.reject(err)
  },
)

export default api
