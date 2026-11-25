const express = require('express');
const os = require('os');
const path = require('path');
const { MongoClient } = require('mongodb');

const app = express();
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// Config sirf environment variables se (koi hard-coded host/IP/password nahi)
const MONGO_URL = process.env.MONGO_URL;
const PORT = process.env.PORT || 3000;
if (!MONGO_URL) {
  console.error('MONGO_URL is not set');
  process.exit(1);
}

const client = new MongoClient(MONGO_URL, { serverSelectionTimeoutMS: 3000 });
const col = client.db().collection('calculations'); // db name URL se aata hai (emidb)

const podName = process.env.HOSTNAME || os.hostname();

function podIp() {
  for (const list of Object.values(os.networkInterfaces())) {
    for (const i of list) {
      if (i.family === 'IPv4' && !i.internal) return i.address;
    }
  }
  return '127.0.0.1';
}

// Server-side validation: sirf positive numbers
function parsePositive(v) {
  if (v === null || v === undefined || v === '') return null;
  const n = Number(v);
  return Number.isFinite(n) && n > 0 ? n : null;
}

// POST /api/emi
app.post('/api/emi', async (req, res) => {
  const body = req.body || {};
  const P = parsePositive(body.principal);
  const rate = parsePositive(body.rate);
  const n = parsePositive(body.months);

  if (P === null || rate === null || n === null || !Number.isInteger(n)) {
    return res.status(400).json({
      error: 'principal, rate and months must be positive numbers (months must be a whole number)'
    });
  }

  const r = rate / 12 / 100;
  const pow = Math.pow(1 + r, n);
  const emi = (P * r * pow) / (pow - 1);
  const totalPayment = emi * n;
  const totalInterest = totalPayment - P;
  const round = (x) => Math.round(x * 100) / 100;

  const result = {
    emi: round(emi),
    totalPayment: round(totalPayment),
    totalInterest: round(totalInterest),
    servedBy: podName,
    podIp: podIp()
  };

  try {
    await col.insertOne({
      principal: P,
      rate: rate,
      months: n,
      emi: result.emi,
      servedBy: podName,
      createdAt: new Date()
    });
    res.json(result);
  } catch (e) {
    console.error(e.message);
    res.status(500).json({ error: 'Database error' });
  }
});

// GET /api/history: last 10, newest first
app.get('/api/history', async (req, res) => {
  try {
    const rows = await col.find({}).sort({ createdAt: -1 }).limit(10).toArray();
    res.json(rows);
  } catch (e) {
    console.error(e.message);
    res.status(500).json({ error: 'Database error' });
  }
});

// GET /health: 200 sirf jab MongoDB reachable ho
app.get('/health', async (req, res) => {
  try {
    await client.db().command({ ping: 1 });
    res.status(200).send('OK');
  } catch (e) {
    res.status(503).send('MongoDB not reachable');
  }
});

app.listen(PORT, () => console.log(`EMI app listening on ${PORT}, pod=${podName}`));
