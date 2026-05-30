/**
 * 前端入口：注册路由 + v-permission 指令。
 */
import { createApp } from "vue";
import App from "./App.vue";
import router from "./router";
import { permissionDirective } from "./directives/permission.js";
import "./styles.css";

const app = createApp(App);

app.directive("permission", permissionDirective);

app.use(router).mount("#app");
