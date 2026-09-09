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

async function listAllKeys(namespace, prefix) {
  let cursor;
  const keys = [];
  do {
    const page = await namespace.list({ prefix, cursor });
    keys.push(...page.keys);
    cursor = page.list_complete ? undefined : page.cursor;
  } while (cursor);
  return keys;
}

async function readCounts(namespace, prefix, field, sectors) {
  const keys = await listAllKeys(namespace, prefix);
  await Promise.all(keys.map(async key => {
    const sector = key.name.replace(new RegExp('^' + prefix), '');
    const count = Number(await namespace.get(key.name) || 0);
    if (!sectors.has(sector)) {
      sectors.set(sector, { sector, count: 0, attempts: 0, found: 0, not_found: 0, legacy_found: 0 });
    }
    sectors.get(sector)[field] += count;
  }));
}

export default {
  async fetch(request, env) {
    if (request.method === 'OPTIONS') return new Response(null, { headers: corsHeaders });

    const url = new URL(request.url);
    if (request.method === 'GET' && url.searchParams.get('summary') === '1') {
      if (env.READ_TOKEN && url.searchParams.get('token') !== env.READ_TOKEN) {
        return jsonResponse({ error: 'Unauthorized' }, { status: 401 });
      }

      const sectorMap = new Map();
      await readCounts(env.POSTCODE_SECTOR_SEARCHES, 'attempt:', 'attempts', sectorMap);
      await readCounts(env.POSTCODE_SECTOR_SEARCHES, 'found:', 'found', sectorMap);
      await readCounts(env.POSTCODE_SECTOR_SEARCHES, 'not_found:', 'not_found', sectorMap);

      // Legacy counts were successful searches stored before outcome tracking existed.
      await readCounts(env.POSTCODE_SECTOR_SEARCHES, 'sector:', 'legacy_found', sectorMap);

      const sectors = Array.from(sectorMap.values()).map(row => {
        const found = row.found + row.legacy_found;
        const attempts = row.attempts + row.legacy_found;
        return {
          sector: row.sector,
          attempts,
          found,
          not_found: row.not_found,
          count: attempts,
        };
      });
      sectors.sort((a, b) => b.attempts - a.attempts || a.sector.localeCompare(b.sector));

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

      const found = body.found !== false;
      const keys = ['attempt:' + sector, (found ? 'found:' : 'not_found:') + sector];
      await Promise.all(keys.map(async key => {
        const current = Number(await env.POSTCODE_SECTOR_SEARCHES.get(key) || 0);
        await env.POSTCODE_SECTOR_SEARCHES.put(key, String(current + 1));
      }));

      return jsonResponse({ ok: true });
    }

    return jsonResponse({ error: 'Not found' }, { status: 404 });
  },
};
