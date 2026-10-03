import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './style.css';

async function boot() {
  const demo = import.meta.env.DEV && new URLSearchParams(location.search).get('demo') === '1';
  if (demo) {
    const { installDemo } = await import('./demo');
    installDemo();
  }
  ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><App demo={demo} /></React.StrictMode>);
}
void boot();
