const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
};

function jsonResponse(body, init = {}) {
  return new Response(JSON.stringify(body), {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...corsHeaders,
      ...(init.headers || {}),
    },
  });
}

function validSector(value) {
  const sector = String(value || '').trim().toUpperCase();
  return /^[A-Z]{1,2}\d[A-Z\d]? \d$/.test(sector) ? sector : '';
}

export default {
  async fetch(request, env) {
    if (request.method === 'OPTIONS') return new Response(null, { headers: corsHeaders });

    const url = new URL(request.url);
    if (request.method === 'GET' && url.searchParams.get('summary') === '1') {
      if (env.READ_TOKEN && url.searchParams.get('token') !== env.READ_TOKEN) {
        return jsonResponse({ error: 'Unauthorized' }, { status: 401 });
      }

      const list = await env.POSTCODE_SECTOR_SEARCHES.list({ prefix: 'sector:' });
      const sectors = await Promise.all(list.keys.map(async key => {
        const count = Number(await env.POSTCODE_SECTOR_SEARCHES.get(key.name) || 0);
        return { sector: key.name.replace(/^sector:/, ''), count };
      }));
      sectors.sort((a, b) => b.count - a.count || a.sector.localeCompare(b.sector));

      return jsonResponse({ sectors });
    }

    if (request.method === 'POST') {
      let body = {};
      try {
        body = await request.json();
      } catch {
        return jsonResponse({ error: 'Invalid JSON' }, { status: 400 });
      }

      const sector = validSector(body.sector);
      if (!sector) return jsonResponse({ error: 'Invalid postcode sector' }, { status: 400 });

      const key = 'sector:' + sector;
      const current = Number(await env.POSTCODE_SECTOR_SEARCHES.get(key) || 0);
      await env.POSTCODE_SECTOR_SEARCHES.put(key, String(current + 1));

      return jsonResponse({ ok: true });
    }

    return jsonResponse({ error: 'Not found' }, { status: 404 });
  },
};
