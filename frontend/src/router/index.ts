import { createRouter, createWebHistory } from "vue-router"

import { can, clearSession, isLoggedIn } from "../auth"
import Forbidden from "../views/Forbidden.vue"
import Home from "../views/Home.vue"
import Login from "../views/Login.vue"
import Monitor from "../views/Monitor.vue"
import Records from "../views/Records.vue"
import Spheroidization from "../views/Spheroidization.vue"
import SpheroidizationDetail from "../views/SpheroidizationDetail.vue"
import Standard from "../views/Standard.vue"
import Users from "../views/Users.vue"

declare module "vue-router" {
  interface RouteMeta {
    title?: string
    /** 免登录（游客可进） */
    public?: boolean
    /** 登录后可进所需的页面权限 */
    permission?: string
  }
}

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/",
      component: Monitor,
      meta: {
        title: "浇注工位监控",
        public: true,
      },
    },
    {
      path: "/records",
      component: Records,
      redirect: "/records/home",
      children: [
        {
          path: "home",
          component: Home,
          meta: {
            title: "首页",
            public: true,
          },
        },
        {
          path: "spheroidization",
          component: Spheroidization,
          meta: {
            title: "球化记录",
            permission: "page:records",
          },
        },
        {
          path: "abnormal",
          component: Spheroidization,
          props: {
            abnormalOnly: true,
          },
          meta: {
            title: "异常记录",
            permission: "page:abnormal",
          },
        },
        {
          path: "standard",
          component: Standard,
          meta: {
            title: "检测标准",
            permission: "page:standard",
          },
        },
        {
          path: "users",
          component: Users,
          meta: {
            title: "用户管理",
            permission: "page:users",
          },
        },
      ],
    },
    {
      path: "/login",
      component: Login,
      meta: {
        title: "登录",
        public: true,
      },
    },
    {
      path: "/403",
      component: Forbidden,
      meta: {
        title: "无权限",
        public: true,
      },
    },
    {
      path: "/spheroidization",
      redirect: "/records/spheroidization",
    },
    {
      // 详情页只要求登录，不挂页面权限
      // （异常记录页的用户只有 page:abnormal，挂 page:records 会让他点不进详情）
      path: "/spheroidization/:id",
      component: SpheroidizationDetail,
      meta: {
        title: "球化记录详情",
      },
    },
    {
      path: "/standard",
      redirect: "/records/standard",
    },
    {
      path: "/:pathMatch(.*)*",
      redirect: "/",
    },
  ],
  scrollBehavior() {
    return {
      top: 0,
    }
  },
})

/**
 * 全局前置守卫：
 * - /records 是父路由，会重定向到 /records/home，
 *   守卫按重定向后的目标路径判断（vue-router 解析重定向后守卫收到的就是目标路由）
 * - 未登录 → 跳登录页（带 redirect）
 * - 已登录但无页面权限 → 跳 /403
 */
router.beforeEach((to) => {
  if (to.meta.public) {
    // 已登录状态访问登录页，直接跳回首页
    if (to.path === "/login" && isLoggedIn()) {
      return { path: "/" }
    }
    return true
  }

  if (!isLoggedIn()) {
    return {
      path: "/login",
      query: {
        redirect: to.fullPath,
      },
    }
  }

  const permission = to.meta.permission
  if (permission && !can(permission)) {
    return { path: "/403" }
  }

  return true
})

// 收到 401（请求层已清登录态）→ 跳登录页
window.addEventListener("auth:expired", () => {
  clearSession()
  const current = router.currentRoute.value
  if (current.path !== "/login") {
    void router.push({
      path: "/login",
      query: {
        redirect: current.fullPath,
      },
    })
  }
})

export default router
