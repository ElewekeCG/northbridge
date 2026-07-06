/**
 * Northbridge Commerce — Catalog Service
 * Express service serving product listings from PostgreSQL.
 *
 * Redis caches the full product list and individual product lookups.
 * Northbridge's catalog is read far more often than it is written —
 * the same ~200 products are fetched on nearly every storefront page
 * view. Before Redis, every page load meant a Postgres query against
 * the products table. At peak traffic this was the second-largest
 * source of database load after session verification. Cache TTL is
 * 60 seconds, which is an acceptable staleness window for product
 * listings (price and stock changes do not need to be instant) and
 * is invalidated explicitly on stock updates from Orders Service.
 */


const express = require('express');
const { Pool } = require('pg');
const { createClient } = require('redis');
const promClient = require('prom-client');

const app = express();
app.use(express.json());

const pool = new Pool({
  connectionString: process.env.DATABASE_URL ||
    'postgresql://northbridge:northbridge_dev@postgres:5432/northbridge_db',
});

const redisClient = createClient({ url: process.env.REDIS_URL || 'redis://redis:6379/0' });
redisClient.on('error', (err) => console.error('Redis Client Error', err));

// ── Prometheus metrics ──────────────────────────────────────────────────
const register = new promClient.Registry();
promClient.collectDefaultMetrics({ register });
const cacheHits = new promClient.Counter({
  name: 'catalog_cache_hits_total',
  help: 'Total number of Redis cache hits for catalog reads',
});
const cacheMisses = new promClient.Counter({
  name: 'catalog_cache_misses_total',
  help: 'Total number of Redis cache misses for catalog reads',
});
register.registerMetric(cacheHits);
register.registerMetric(cacheMisses);

const httpRequestDuration = new promClient.Histogram({
  name: 'http_request_duration_seconds',
  help: 'Duration of HTTP requests in seconds',
  labelNames: ['method', 'route', 'status_code'],
});
register.registerMetric(httpRequestDuration);

app.use((req, res, next) => {
  const end = httpRequestDuration.startTimer();
  res.on('finish', () => {
    end({ method: req.method, route: req.path, status_code: res.statusCode });
  });
  next();
});

const CACHE_TTL_SECONDS = 60;

async function ensureTable() {
  await pool.query(`
    CREATE TABLE IF NOT EXISTS products (
      id SERIAL PRIMARY KEY,
      sku VARCHAR(50) UNIQUE NOT NULL,
      name VARCHAR(200) NOT NULL,
      description TEXT,
      price NUMERIC(10,2) NOT NULL,
      stock INTEGER NOT NULL DEFAULT 0,
      category VARCHAR(100),
      created_at TIMESTAMP DEFAULT NOW()
    )
  `);

  const { rows } = await pool.query('SELECT COUNT(*) FROM products');
  if (parseInt(rows[0].count) === 0) {
    const seed = [
      ['NBC-001', 'Wireless Noise-Cancelling Headphones', 'Over-ear, 30hr battery', 149.99, 75, 'Electronics'],
      ['NBC-002', 'Ergonomic Office Chair', 'Adjustable lumbar support', 219.00, 40, 'Furniture'],
      ['NBC-003', 'Stainless Steel Water Bottle', '750ml, insulated', 18.99, 300, 'Lifestyle'],
      ['NBC-004', 'Mechanical Keyboard', 'Hot-swappable switches', 89.99, 110, 'Electronics'],
      ['NBC-005', 'Standing Desk Converter', 'Height adjustable', 159.00, 55, 'Furniture'],
      ['NBC-006', 'Bluetooth Speaker', 'Waterproof, 12hr battery', 45.50, 180, 'Electronics'],
      ['NBC-007', 'Yoga Mat Premium', '6mm thick, non-slip', 29.99, 220, 'Fitness'],
    ];
    for (const p of seed) {
      await pool.query(
        'INSERT INTO products (sku, name, description, price, stock, category) VALUES ($1,$2,$3,$4,$5,$6)',
        p
      );
    }
    console.log('Seeded product catalog');
  }
}


// ── Routes ───────────────────────────────────────────────────────────────
async function healthHandler(req, res) {
  let dbOk = true, redisOk = true;
  try { await pool.query('SELECT 1'); } catch { dbOk = false; }
  try { await redisClient.ping(); } catch { redisOk = false; }
  const status = dbOk && redisOk ? 'ok' : 'degraded';
  res.status(dbOk && redisOk ? 200 : 503).json({
    status, db: dbOk ? 'ok' : 'error', redis: redisOk ? 'ok' : 'error', service: 'catalog-service'
  });
}

app.get('/healthz', healthHandler);
app.get('/api/catalog/healthz', healthHandler);

app.get('/metrics', async (req, res) => {
  res.set('Content-Type', register.contentType);
  res.end(await register.metrics());
});

app.get('/api/catalog/products', async (req, res) => {
  try {
    const { category } = req.query;
    const cacheKey = `catalog:products:${category || 'all'}`;

    const cached = await redisClient.get(cacheKey);
    if (cached) {
      cacheHits.inc();
      return res.status(200).json(JSON.parse(cached));
    }
    cacheMisses.inc();

    let query = 'SELECT * FROM products';
    const params = [];
    if (category) {
      query += ' WHERE category = $1';
      params.push(category);
    }
    query += ' ORDER BY id';
    const { rows } = await pool.query(query, params);
    const result = { count: rows.length, products: rows };

    await redisClient.setEx(cacheKey, CACHE_TTL_SECONDS, JSON.stringify(result));
    res.status(200).json(result);
  } catch (err) {
    console.error('Error fetching products:', err);
    res.status(500).json({ error: 'Failed to fetch products' });
  }
});

app.get('/api/catalog/products/:id', async (req, res) => {
  try {
    const cacheKey = `catalog:product:${req.params.id}`;
    const cached = await redisClient.get(cacheKey);
    if (cached) {
      cacheHits.inc();
      return res.status(200).json(JSON.parse(cached));
    }
    cacheMisses.inc();

    const { rows } = await pool.query('SELECT * FROM products WHERE id = $1', [req.params.id]);
    if (rows.length === 0) {
      return res.status(404).json({ error: 'Product not found' });
    }
    await redisClient.setEx(cacheKey, CACHE_TTL_SECONDS, JSON.stringify(rows[0]));
    res.status(200).json(rows[0]);
  } catch (err) {
    res.status(500).json({ error: 'Failed to fetch product' });
  }
});

app.post('/api/catalog/products', async (req, res) => {
  const { sku, name, description, price, stock, category } = req.body;
  if (!sku || !name || price === undefined) {
    return res.status(400).json({ error: 'sku, name, and price are required' });
  }
  try {
    const { rows } = await pool.query(
      'INSERT INTO products (sku, name, description, price, stock, category) VALUES ($1,$2,$3,$4,$5,$6) RETURNING *',
      [sku, name, description || '', price, stock || 0, category || 'Uncategorised']
    );
    await invalidateListCache();
    res.status(201).json(rows[0]);
  } catch (err) {
    if (err.code === '23505') {
      return res.status(409).json({ error: 'SKU already exists' });
    }
    res.status(500).json({ error: 'Failed to create product' });
  }
});

// Internal endpoint — called by orders-service. Invalidates the cache,
// for this product and the list cache since stock has changed.
app.patch('/api/catalog/products/:id/stock', async (req, res) => {
  const { delta } = req.body;
  try {
    const { rows } = await pool.query(
      'UPDATE products SET stock = stock + $1 WHERE id = $2 AND stock + $1 >= 0 RETURNING *',
      [delta, req.params.id]
    );
    if (rows.length === 0) {
      return res.status(409).json({ error: 'Insufficient stock or product not found' });
    }
    await redisClient.del(`catalog:product:${req.params.id}`);
    await invalidateListCache();
    res.status(200).json(rows[0]);
  } catch (err) {
    res.status(500).json({ error: 'Failed to update stock' });
  }
});

async function invalidateListCache() {
  const keys = await redisClient.keys('catalog:products:*');
  if (keys.length > 0) {
    await redisClient.del(keys);
  }
}

const PORT = process.env.PORT || 4000;

if (require.main === module) {
  redisClient.connect()
    .then(() => ensureTable())
    .then(() => {
      app.listen(PORT, () => console.log(`Catalog Service listening on port ${PORT}`));
    })
    .catch((err) => {
      console.error('Failed to initialise:', err);
      process.exit(1);
    });
}

module.exports = { app, pool, redisClient, ensureTable };
