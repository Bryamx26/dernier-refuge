import '@fontsource/silkscreen/400.css';
import '@fontsource/silkscreen/700.css';
import '@fontsource/vt323/400.css';
import './ui/theme/theme.css';

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';

const rootElement = document.getElementById('root');
if (!rootElement) throw new Error('Élément #root introuvable');

createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
