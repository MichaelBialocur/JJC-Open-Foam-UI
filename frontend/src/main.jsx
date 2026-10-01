import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import Workbench from './Workbench.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <Workbench />
  </StrictMode>,
)
