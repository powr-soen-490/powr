// Source-File AI Declaration
// AI contribution: 50% or more AI-generated

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router'
import App from './App.tsx'
import { FeatureFlagsProvider } from './providers/FeatureFlagsProvider'
import './styles/global.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <FeatureFlagsProvider>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </FeatureFlagsProvider>
  </StrictMode>,
)
