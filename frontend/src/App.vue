<template>
  <div>
    <nav class="navbar">
      <div class="logo">
        球化监测系统
      </div>

      <div class="nav-links">
        <router-link to="/">
          首页
        </router-link>

        <router-link to="/spheroidization">
          球化记录
        </router-link>

        <router-link to="/standard">
          检测标准
        </router-link>
      </div>
    </nav>

    <main class="content">
      <router-view />
    </main>
  </div>
</template>

<style scoped>
.navbar {
  display: flex;
  align-items: center;
  justify-content: space-between;

  padding: 16px 32px;

  border-bottom: 1px solid #ddd;
}

.logo {
  font-size: 20px;
  font-weight: bold;
}

.nav-links {
  display: flex;
  gap: 24px;
}

.nav-links a {
  color: #333;
  text-decoration: none;
}

.nav-links a.router-link-active {
  font-weight: bold;
}

.content {
  padding: 32px;
}
</style>