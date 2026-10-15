import { createApp } from 'vue'
import App from './app/App.vue'
import './styles/main.css'
import { VueQueryPlugin } from '@tanstack/vue-query'
createApp(App)
  .use(VueQueryPlugin, {
    queryClientConfig: {
      defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
    },
  })
  .mount('#app')
