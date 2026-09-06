import { createRouter, createWebHistory } from "vue-router"

import Home from "../views/Home.vue"
import Spheroidization from "../views/Spheroidization.vue"
import SpheroidizationDetail from "../views/SpheroidizationDetail.vue"
import Standard from "../views/Standard.vue"

const router = createRouter({
  history: createWebHistory(),

  routes: [
    {
      path: "/",
      component: Home,
    },
    {
      path: "/spheroidization",
      component: Spheroidization,
    },
    {
      path: "/spheroidization/:id",
      component: SpheroidizationDetail,
    },
    {
      path: "/standard",
      component: Standard,
    },
  ],
})

export default router