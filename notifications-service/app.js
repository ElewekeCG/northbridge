/**
 * Northbridge Commerce — Notifications Service
 * Mock email/SMS dispatch on order events. In production this would
 * integrate SES/Twilio — here it logs and stores the notification
 * record, which is sufficient to demonstrate the event-driven pattern
 * and is what interns wire Orders Service to call.
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
const notificationsSent = new promClient.Counter({
  name: 'notifications_sent_total',
  help: 'Total notifications sent',
  labelNames: ['type'],
});
register.registerMetric(notificationsSent);

async function ensureTable() {
  await pool.query(`
    CREATE TABLE IF NOT EXISTS notifications (
      id SERIAL PRIMARY KEY,
      user_id INTEGER NOT NULL,
      type VARCHAR(50) NOT NULL,
      message TEXT NOT NULL,
      sent_at TIMESTAMP DEFAULT NOW()
    )
  `);
}

async function healthHandler(req, res) {
  let dbOk = true, redisOk = true;
  try { await pool.query('SELECT 1'); } catch { dbOk = false; }
  const status = dbOk && redisOk ? 'ok' : 'degraded';
  res.status(dbOk && redisOk ? 200 : 503).json({
    status, db: dbOk ? 'ok' : 'error', redis: redisOk ? 'ok' : 'error', service: 'notifications-service'
  });
}

app.get('/healthz', healthHandler);
app.get('/api/notifications/healthz', healthHandler);

app.get('/metrics', async (req, res) => {
  res.set('Content-Type', register.contentType);
  res.end(await register.metrics());
});

app.post('/api/notifications/order-confirmed', async (req, res) => {
  const { user_id, order_id, total } = req.body;
  const message = `Order #${order_id} confirmed. Total: £${parseFloat(total).toFixed(2)}. Thank you for shopping with Northbridge.`;

  try {
    const { rows } = await pool.query(
      'INSERT INTO notifications (user_id, type, message) VALUES ($1,$2,$3) RETURNING *',
      [user_id, 'order_confirmed', message]
    );
    notificationsSent.inc({ type: 'order_confirmed' });
    console.log(`[NOTIFY] User ${user_id}: ${message}`);
    res.status(200).json({ sent: true, notification: rows[0] });
  } catch (err) {
    console.error('Notification error:', err);
    res.status(500).json({ error: 'Failed to send notification' });
  }
});

app.get('/api/notifications/user/:userId', async (req, res) => {
  try {
    const { rows } = await pool.query(
      'SELECT * FROM notifications WHERE user_id = $1 ORDER BY sent_at DESC LIMIT 20',
      [req.params.userId]
    );
    res.status(200).json({ count: rows.length, notifications: rows });
  } catch (err) {
    res.status(500).json({ error: 'Failed to fetch notifications' });
  }
});

const PORT = process.env.PORT || 4002;

if (require.main === module) {
  ensureTable()
    .then(() => app.listen(PORT, () => console.log(`Notifications Service listening on port ${PORT}`)))
    .catch((err) => { console.error('Init failed:', err); process.exit(1); });
}

module.exports = { app, pool };
