import { createRouter, createWebHistory } from "vue-router"

import Home from "../views/Home.vue"
import Monitor from "../views/Monitor.vue"
import Records from "../views/Records.vue"
import Spheroidization from "../views/Spheroidization.vue"
import SpheroidizationDetail from "../views/SpheroidizationDetail.vue"
import Standard from "../views/Standard.vue"

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/",
      component: Monitor,
      meta: {
        title: "浇注工位监控",
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
          },
        },
        {
          path: "spheroidization",
          component: Spheroidization,
          meta: {
            title: "球化记录",
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
          },
        },
        {
          path: "standard",
          component: Standard,
          meta: {
            title: "检测标准",
          },
        },
      ],
    },
    {
      path: "/spheroidization",
      redirect: "/records/spheroidization",
    },
    {
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

export default router
