/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#fef3ff',
          100: '#fde8ff',
          200: '#fad0fe',
          300: '#f5a9fc',
          400: '#ed74f7',
          500: '#de46ee',
          600: '#c027d4',
          700: '#a01bb0',
          800: '#841990',
          900: '#6d1a76',
          950: '#48054f',
        },
        surface: {
          DEFAULT: '#0f0f11',
          1: '#18181c',
          2: '#222227',
          3: '#2c2c32',
        },
      },
      fontFamily: {
        sans: ['-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Cascadia Code', 'Consolas', 'monospace'],
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
    },
  },
  plugins: [],
}
