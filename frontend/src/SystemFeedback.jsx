import { useEffect, useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useLocation } from 'react-router-dom';
import { AlertCircle, CheckCircle2, LoaderCircle, LogOut, X } from 'lucide-react';
import { activeRequests } from './requestFeedback.mjs';
import { formatUserFacingMessage } from './errorMessages.mjs';

export function LoadingScreen({ message = 'Please wait…' }) {
  return createPortal(<div className="pointer-events-none fixed inset-x-0 top-0 z-[30000] h-1 overflow-hidden bg-transparent" role="status" aria-live="polite" aria-busy="true"><span className="block h-full w-1/3 rounded-full bg-amber-800 animate-[villa-feedback-loading_1.2s_ease-in-out_infinite] motion-reduce:animate-none" aria-hidden="true"/><span className="sr-only">{message}</span></div>, document.body);
}

export function AlertMessage({ message, type = 'error', dismiss }) {
  const success = type === 'success';
  const Icon = success ? CheckCircle2 : AlertCircle;
  return <div role={success ? 'status' : 'alert'} className={`flex items-start gap-2 rounded-lg border px-3 py-2.5 text-xs shadow-md ${success ? 'border-emerald-200 bg-emerald-50 text-emerald-900' : 'border-stone-200 bg-white text-stone-700'}`}><Icon className={`mt-0.5 h-4 w-4 shrink-0 ${success ? '' : 'text-amber-800'}`} aria-hidden="true"/><span className="min-w-0 flex-1 whitespace-pre-wrap break-words">{formatUserFacingMessage(message)}</span>{dismiss && <button type="button" aria-label="Dismiss alert" className="rounded-md bg-transparent p-1 text-inherit focus-visible:outline-2" onClick={dismiss}><X size={16}/></button>}</div>;
}

export function ConfirmAction({ open, busy = false, cancel, confirm, titleText = 'Sign out?', message = 'You’ll need to sign in again to access your workspace.', confirmLabel = 'Sign out', cancelLabel = 'Stay signed in' }) {
  const dialog = useRef(null);
  const title = useId();
  const description = useId();
  useEffect(() => {
    const node = dialog.current;
    if (!open || !node) return;
    const previous = document.activeElement;
    node.showModal();
    return () => { node.close(); previous?.focus(); };
  }, [open]);
  if (!open) return null;
  const Icon = busy ? LoaderCircle : LogOut;
  return createPortal(<dialog ref={dialog} aria-labelledby={title} aria-describedby={description} onCancel={event => { event.preventDefault(); if (!busy) cancel(); }} className="m-auto w-[calc(100%-2rem)] max-w-sm rounded-2xl border border-stone-200 bg-white p-7 text-stone-900 shadow-2xl backdrop:bg-stone-950/40 backdrop:backdrop-blur-sm"><Icon className={`mb-4 h-8 w-8 text-amber-800 ${busy ? 'animate-spin motion-reduce:animate-none' : ''}`} aria-hidden="true"/><h2 id={title} className="text-xl font-bold">{titleText}</h2><p id={description} className="mt-2 text-sm text-stone-600">{message}</p><div className="mt-6 flex justify-end gap-3"><button type="button" autoFocus disabled={busy} onClick={cancel} className="rounded-xl border border-stone-300 bg-white px-4 py-3 text-sm font-semibold text-stone-700 disabled:opacity-50">{cancelLabel}</button><button type="button" disabled={busy} onClick={confirm} className="rounded-xl border border-amber-900 bg-amber-900 px-4 py-3 text-sm font-semibold text-white disabled:opacity-50">{busy ? 'Please wait…' : confirmLabel}</button></div></dialog>, document.body);
}

export function ConfirmSignOut(props) { return <ConfirmAction {...props}/>; }

export default function SystemFeedback() {
  const { pathname } = useLocation();
  const [pending, setPending] = useState(activeRequests);
  const [visible, setVisible] = useState(false);
  const [alert, setAlert] = useState(null);
  useEffect(() => {
    const listener = event => {
      if (event.detail.kind === 'pending') setPending(event.detail.count);
      else if (event.detail.kind === 'alert') setAlert(event.detail);
      else if (event.detail.kind === 'dismiss-alert') {
        setAlert(current => current &&
          formatUserFacingMessage(current.message) === formatUserFacingMessage(event.detail.message)
          ? null
          : current);
      }
    };
    window.addEventListener('villa:feedback', listener);
    return () => window.removeEventListener('villa:feedback', listener);
  }, []);
  useEffect(() => {
    const timer = setTimeout(() => setVisible(pending > 0), pending ? 350 : 0);
    return () => clearTimeout(timer);
  }, [pending]);
  const showLoading = visible && pathname !== '/admin-login';
  return <>{showLoading && <LoadingScreen message="Processing your request…"/>}{alert && !showLoading && createPortal(<div className="fixed right-4 bottom-4 left-4 z-[31000] mx-auto max-w-lg"><AlertMessage message={alert.message} type={alert.type} dismiss={() => setAlert(null)}/></div>, document.body)}</>;
}
