/** Incremental SSE parser: handles chunk boundaries, CRLF and comment heartbeats. */
export function createSSEParser(onEvent) {
  let buffer = '';
  return chunk => {
    buffer += chunk;
    buffer = buffer.replace(/\r\n/g, '\n');
    let boundary;
    while ((boundary = buffer.indexOf('\n\n')) >= 0) {
      const frame = buffer.slice(0, boundary); buffer = buffer.slice(boundary + 2);
      let event = 'message'; const data = [];
      for (const line of frame.split('\n')) {
        if (line.startsWith('event:')) event = line.slice(6).trim();
        else if (line.startsWith('data:')) data.push(line.slice(5).replace(/^ /, ''));
      }
      if (data.length) { try { onEvent(event, JSON.parse(data.join('\n'))); } catch { /* Malformed frames never break reconnect. */ } }
    }
    if (buffer.length > 65536) throw new Error('Live event frame too large');
  };
}

/** Coalesce bursts; a change received during a refresh schedules one follow-up. */
export function coalescedRefresh(callback, delay = 220) {
  let timer = null, active = false, dirty = false, stopped = false;
  async function run() {
    timer = null;
    if (stopped) return;
    if (active) { dirty = true; return; }
    active = true; dirty = false;
    try { await callback(); } catch { /* Existing page handlers display errors. */ }
    finally { active = false; if (dirty && !stopped) timer = setTimeout(run, delay); }
  }
  const request = () => { if (stopped) return; dirty = true; if (!timer && !active) timer = setTimeout(run, delay); };
  request.cancel = () => { stopped = true; clearTimeout(timer); };
  return request;
}

/** One active snapshot read; preserve one trailing read for changes mid-flight. */
export function singleFlightRefresh(callback) {
  let current = null, trailing = null;
  const run = (...args) => {
    if (current) { trailing = args; return current; }
    current = Promise.resolve().then(() => callback(...args)).finally(() => {
      current = null;
      if (trailing) { const next = trailing; trailing = null; run(...next).catch(() => {}); }
    });
    return current;
  };
  return run;
}
