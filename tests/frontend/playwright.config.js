// Strona jest statyczna i bez budowania, więc serwer testowy to zwykły http.server
// na katalogu repozytorium — dokładnie to, co robi GitHub Pages.
const { defineConfig, devices } = require('@playwright/test');

module.exports = defineConfig({
  testDir: '.',
  timeout: 30000,
  expect: { timeout: 7000 },
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,          // jeden powtórek na drgnięcia timingu w CI
  reporter: process.env.CI ? [['github'], ['list']] : [['list']],
  use: {
    baseURL: 'http://127.0.0.1:8123',
    /* Service worker musi być wyłączony, bo przechwytuje fetch strony i idzie prosto
       do sieci, omijając podstawione dane. Objawiało się to tak, że manifest przychodził
       z fikstury, a CSV prawdziwy z repozytorium — czyli identyfikatory urządzeń się nie
       zgadzały i pokoje wyglądały na martwe. Sam worker ma własny test niżej. */
    serviceWorkers: 'block',
    // Furtka dla środowisk, które mają już własne Chromium i nie chcą pobierać kolejnego
    // (kontenery deweloperskie). W CI zmiennej nie ma, więc idzie zwykłe `playwright install`.
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM_PATH
      ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH } : {},
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'python3 serwer.py 8123',
    url: 'http://127.0.0.1:8123/index.html',
    reuseExistingServer: !process.env.CI,
    stdout: 'ignore',
  },
});
