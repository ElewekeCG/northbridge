/**
 * Northbridge Commerce — Payments Service
 * Mock payment processing. Simulates a card charge with realistic
 * failure modes (insufficient funds simulation, card validation)
 * without integrating a real payment processor — appropriate for
 * a training environment.
 */

const express = require('express');
const { Pool } = require('pg');
const promClient = require('prom-client');

const app = express();
app.use(express.json());

const pool = new Pool({
  connectionString: process.env.DATABASE_URL ||
    'postgresql://northbridge:northbridge_dev@postgres:5432/northbridge_db',
});

const register = new promClient.Registry();
promClient.collectDefaultMetrics({ register });
const paymentsTotal = new promClient.Counter({
  name: 'payments_processed_total',
  help: 'Total payments processed',
  labelNames: ['status'],
});
register.registerMetric(paymentsTotal);

async function ensureTable() {
  await pool.query(`
    CREATE TABLE IF NOT EXISTS payments (
      id SERIAL PRIMARY KEY,
      user_id INTEGER NOT NULL,
      amount NUMERIC(10,2) NOT NULL,
      card_last4 VARCHAR(4) NOT NULL,
      status VARCHAR(20) NOT NULL,
      created_at TIMESTAMP DEFAULT NOW()
    )
  `);
}

app.get('/healthz', async (req, res) => {
  try {
    await pool.query('SELECT 1');
    res.status(200).json({ status: 'ok', db: 'ok', service: 'payments-service' });
  } catch {
    res.status(503).json({ status: 'degraded', db: 'error' });
  }
});

app.get('/metrics', async (req, res) => {
  res.set('Content-Type', register.contentType);
  res.end(await register.metrics());
});

app.post('/api/payments/charge', async (req, res) => {
  const { amount, card_last4, user_id } = req.body;
  if (!amount || !card_last4 || !user_id) {
    return res.status(400).json({ error: 'amount, card_last4, and user_id are required' });
  }

  // Simulated decline: card ending in 0000 always declines (test card)
  const declined = card_last4 === '0000';
  const status = declined ? 'declined' : 'success';

  try {
    const { rows } = await pool.query(
      'INSERT INTO payments (user_id, amount, card_last4, status) VALUES ($1,$2,$3,$4) RETURNING *',
      [user_id, amount, card_last4, status]
    );
    paymentsTotal.inc({ status });

    if (declined) {
      return res.status(402).json({ error: 'Payment declined', payment: rows[0] });
    }
    res.status(200).json({ success: true, payment: rows[0] });
  } catch (err) {
    console.error('Payment processing error:', err);
    res.status(500).json({ error: 'Payment processing failed' });
  }
});

app.get('/api/payments/:id', async (req, res) => {
  try {
    const { rows } = await pool.query('SELECT * FROM payments WHERE id = $1', [req.params.id]);
    if (rows.length === 0) return res.status(404).json({ error: 'Payment not found' });
    res.status(200).json(rows[0]);
  } catch (err) {
    res.status(500).json({ error: 'Failed to fetch payment' });
  }
});

const PORT = process.env.PORT || 4001;

if (require.main === module) {
  ensureTable()
    .then(() => app.listen(PORT, () => console.log(`Payments Service listening on port ${PORT}`)))
    .catch((err) => { console.error('Init failed:', err); process.exit(1); });
}

module.exports = { app, pool };
