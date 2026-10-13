-- Deterministic mock data for the Support agent (REQ-SUP-02). Fictitious merchants only.
-- Dates are relative to the session setting `app.seed_date` (set by app.db.migrate.apply_seed):
-- d = reference day ("today"), d - 1 = "yesterday". Local times are America/Sao_Paulo.
-- Idempotent: users and decline codes are upserted; the seed merchants' rows are deleted and
-- reinserted, so a new reference date moves every date consistently.
-- Each merchant has clearly different amounts so a cross-customer leak is easy to detect.

INSERT INTO users (id, role, display_name) VALUES
    ('cliente1988', 'merchant', 'Loja Exemplo 1988'),
    ('cliente2024', 'merchant', 'Loja Exemplo 2024'),
    ('cliente3033', 'merchant', 'Loja Exemplo 3033'),
    ('operador01', 'operator', 'Operador 01'),
    ('admin01', 'admin', 'Admin 01')
ON CONFLICT (id) DO NOTHING;

INSERT INTO decline_codes (code, description_pt, description_en, action_pt, action_en) VALUES
    ('05', 'Transação não autorizada pelo banco emissor do cartão.',
           'Do not honor: the card issuer declined the transaction.',
           'Peça ao cliente para falar com o banco emissor ou usar outro cartão.',
           'Ask the customer to contact the issuing bank or use another card.'),
    ('51', 'Saldo ou limite insuficiente no cartão.',
           'Insufficient funds or credit limit on the card.',
           'Peça outro cartão, outra forma de pagamento (como Pix) ou um valor menor.',
           'Ask for another card, another payment method (such as Pix) or a smaller amount.'),
    ('57', 'Transação não permitida para este cartão.',
           'Transaction not permitted to the cardholder.',
           'Peça ao cliente para confirmar com o banco se o cartão aceita essa compra, ou use outro cartão.',
           'Ask the customer to check with the bank whether the card allows this purchase, or use another card.')
ON CONFLICT (code) DO UPDATE SET
    description_pt = EXCLUDED.description_pt,
    description_en = EXCLUDED.description_en,
    action_pt = EXCLUDED.action_pt,
    action_en = EXCLUDED.action_en;

-- Cascades to terminals, transactions and settlements of the seed merchants.
DELETE FROM merchants WHERE user_id IN ('cliente1988', 'cliente2024', 'cliente3033');

INSERT INTO merchants (user_id, trade_name, document_masked, plan, settlement_days,
                       anticipation_enabled) VALUES
    ('cliente1988', 'Mercadinho Sol Nascente', '**.***.***/0001-**', 'Get Smart', 1, true),
    ('cliente2024', 'Café Lua Cheia', '**.***.***/0001-**', 'Get Clássica', 30, false),
    ('cliente3033', 'Ótica Horizonte', '**.***.***/0001-**', 'Get Mini', 1, false);

INSERT INTO terminals (id, merchant_id, model, serial, connectivity, status, last_seen_at,
                       last_error)
SELECT v.id, v.merchant_id, v.model, v.serial, v.connectivity, v.status,
       (r.d + v.day_offset + v.at_time) AT TIME ZONE 'America/Sao_Paulo', v.last_error
FROM (SELECT current_setting('app.seed_date')::date AS d) r,
     (VALUES
        ('T1988-01', 'cliente1988', 'Get Smart', 'SN1988A', 'wifi', 'online', -1, time '18:05', NULL),
        ('T1988-02', 'cliente1988', 'Get Mini', 'SN1988B', 'chip_4g', 'offline', -1, time '07:40', 'NO_SIGNAL'),
        ('T2024-01', 'cliente2024', 'Get Clássica', 'SN2024A', 'ethernet', 'online', -1, time '12:00', NULL),
        ('T3033-01', 'cliente3033', 'Get Smart', 'SN3033A', 'wifi', 'offline', -2, time '19:00', 'WIFI_AUTH_FAILED')
     ) AS v(id, merchant_id, model, serial, connectivity, status, day_offset, at_time, last_error);

INSERT INTO transactions (id, merchant_id, terminal_id, created_at, amount_cents, method,
                          installments, status, decline_code)
SELECT v.id, v.merchant_id, v.terminal_id,
       (r.d + v.day_offset + v.at_time) AT TIME ZONE 'America/Sao_Paulo',
       v.amount_cents, v.method, v.installments, v.status, v.decline_code
FROM (SELECT current_setting('app.seed_date')::date AS d) r,
     (VALUES
        ('tx-1988-001', 'cliente1988', 'T1988-01', -1, time '09:12', 15000, 'credit', 1, 'approved', NULL),
        ('tx-1988-002', 'cliente1988', 'T1988-01', -1, time '14:30', 8990, 'debit', 1, 'approved', NULL),
        ('tx-1988-003', 'cliente1988', 'T1988-01', -1, time '16:45', 23450, 'credit', 3, 'approved', NULL),
        ('tx-1988-004', 'cliente1988', 'T1988-01', -1, time '18:05', 12000, 'credit', 1, 'declined', '51'),
        ('tx-1988-005', 'cliente1988', 'T1988-01', -3, time '11:00', 5000, 'pix', 1, 'approved', NULL),
        ('tx-1988-006', 'cliente1988', 'T1988-02', -5, time '10:20', 30000, 'debit', 1, 'approved', NULL),
        ('tx-2024-001', 'cliente2024', 'T2024-01', -1, time '10:00', 77777, 'credit', 1, 'approved', NULL),
        ('tx-2024-002', 'cliente2024', NULL, -1, time '12:00', 44444, 'payment_link', 2, 'approved', NULL),
        ('tx-2024-003', 'cliente2024', 'T2024-01', -2, time '13:00', 22222, 'credit', 1, 'declined', '05'),
        ('tx-3033-001', 'cliente3033', 'T3033-01', -1, time '15:00', 33033, 'debit', 1, 'approved', NULL),
        ('tx-3033-002', 'cliente3033', 'T3033-01', -4, time '09:00', 66066, 'credit', 1, 'declined', '57')
     ) AS v(id, merchant_id, terminal_id, day_offset, at_time, amount_cents, method, installments,
            status, decline_code);

-- Net of fees; expected_date = sale day + the merchant's settlement_days.
INSERT INTO settlements (id, merchant_id, transaction_id, expected_date, amount_cents, status)
SELECT v.id, v.merchant_id, v.transaction_id, r.d + v.day_offset, v.amount_cents, v.status
FROM (SELECT current_setting('app.seed_date')::date AS d) r,
     (VALUES
        ('stl-1988-001', 'cliente1988', 'tx-1988-001', 0, 14625, 'scheduled'),
        ('stl-1988-002', 'cliente1988', 'tx-1988-002', 0, 8810, 'scheduled'),
        ('stl-1988-003', 'cliente1988', 'tx-1988-003', 0, 22630, 'scheduled'),
        ('stl-1988-005', 'cliente1988', 'tx-1988-005', -2, 4950, 'paid'),
        ('stl-1988-006', 'cliente1988', 'tx-1988-006', -4, 29400, 'paid'),
        ('stl-2024-001', 'cliente2024', 'tx-2024-001', 29, 75444, 'scheduled'),
        ('stl-2024-002', 'cliente2024', 'tx-2024-002', 29, 43110, 'scheduled'),
        ('stl-3033-001', 'cliente3033', 'tx-3033-001', 0, 32372, 'scheduled')
     ) AS v(id, merchant_id, transaction_id, day_offset, amount_cents, status);
