-- Multi-tenant database schema extensions
-- This file extends the existing schema with tenant support

-- Create tenants table
CREATE TABLE IF NOT EXISTS tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'suspended', 'inactive')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    settings JSONB DEFAULT '{}',
    limits JSONB DEFAULT '{}'
);

-- Create tenant API keys table
CREATE TABLE IF NOT EXISTS tenant_api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    key_name VARCHAR(255) NOT NULL,
    api_key VARCHAR(255) UNIQUE NOT NULL,
    permissions JSONB DEFAULT '{}',
    rate_limit_per_minute INTEGER DEFAULT 1000,
    rate_limit_per_hour INTEGER DEFAULT 10000,
    rate_limit_per_day INTEGER DEFAULT 100000,
    status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'suspended', 'revoked')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE,
    last_used_at TIMESTAMP WITH TIME ZONE
);

-- Create tenant devices table
CREATE TABLE IF NOT EXISTS tenant_devices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    device_id VARCHAR(255) NOT NULL,
    device_name VARCHAR(255),
    device_type VARCHAR(100),
    status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'suspended')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    settings JSONB DEFAULT '{}',
    UNIQUE(tenant_id, device_id)
);

-- Add tenant_id to existing tables
ALTER TABLE raw_frames ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES tenants(id);
ALTER TABLE telemetry_flat ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES tenants(id);
ALTER TABLE decode_errors ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES tenants(id);
ALTER TABLE can_raw ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES tenants(id);
ALTER TABLE can_signals ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES tenants(id);

-- Create composite indexes for tenant-based queries
CREATE INDEX IF NOT EXISTS idx_raw_frames_tenant_device_time 
ON raw_frames(tenant_id, device_hint, received_at DESC);

CREATE INDEX IF NOT EXISTS idx_telemetry_flat_tenant_device_time 
ON telemetry_flat(tenant_id, device_hint, received_at DESC);

CREATE INDEX IF NOT EXISTS idx_can_raw_tenant_device_time 
ON can_raw(tenant_id, device_id, recv_time DESC);

CREATE INDEX IF NOT EXISTS idx_can_signals_tenant_time_pgn 
ON can_signals(tenant_id, signal_time DESC, pgn, spn);

CREATE INDEX IF NOT EXISTS idx_decode_errors_tenant_time 
ON decode_errors(tenant_id, created_at DESC);

-- Create tenant-specific partitions for can_raw (example)
-- This would be done dynamically for each tenant
CREATE TABLE IF NOT EXISTS can_raw_tenant_template (
    LIKE can_raw INCLUDING ALL
) PARTITION BY RANGE (recv_time);

-- Create tenant usage tracking table
CREATE TABLE IF NOT EXISTS tenant_usage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    frames_received BIGINT DEFAULT 0,
    frames_processed BIGINT DEFAULT 0,
    can_frames_received BIGINT DEFAULT 0,
    can_signals_decoded BIGINT DEFAULT 0,
    api_requests BIGINT DEFAULT 0,
    storage_bytes BIGINT DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(tenant_id, date)
);

-- Create tenant quotas table
CREATE TABLE IF NOT EXISTS tenant_quotas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    quota_type VARCHAR(100) NOT NULL,
    quota_limit BIGINT NOT NULL,
    quota_used BIGINT DEFAULT 0,
    quota_reset_date DATE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(tenant_id, quota_type)
);

-- Create tenant billing table
CREATE TABLE IF NOT EXISTS tenant_billing (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    billing_period_start DATE NOT NULL,
    billing_period_end DATE NOT NULL,
    frames_received BIGINT DEFAULT 0,
    frames_processed BIGINT DEFAULT 0,
    can_frames_received BIGINT DEFAULT 0,
    can_signals_decoded BIGINT DEFAULT 0,
    api_requests BIGINT DEFAULT 0,
    storage_bytes BIGINT DEFAULT 0,
    cost_per_frame DECIMAL(10, 6) DEFAULT 0.000001,
    cost_per_can_frame DECIMAL(10, 6) DEFAULT 0.000002,
    cost_per_api_request DECIMAL(10, 6) DEFAULT 0.000001,
    cost_per_storage_gb DECIMAL(10, 6) DEFAULT 0.01,
    total_cost DECIMAL(10, 2) DEFAULT 0.00,
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'calculated', 'billed', 'paid')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create Row Level Security (RLS) policies
-- Enable RLS on tenant-specific tables
ALTER TABLE raw_frames ENABLE ROW LEVEL SECURITY;
ALTER TABLE telemetry_flat ENABLE ROW LEVEL SECURITY;
ALTER TABLE can_raw ENABLE ROW LEVEL SECURITY;
ALTER TABLE can_signals ENABLE ROW LEVEL SECURITY;
ALTER TABLE decode_errors ENABLE ROW LEVEL SECURITY;

-- Create RLS policies for tenant isolation
CREATE POLICY tenant_isolation_raw_frames ON raw_frames
    USING (tenant_id = current_setting('app.tenant_id')::uuid);

CREATE POLICY tenant_isolation_telemetry_flat ON telemetry_flat
    USING (tenant_id = current_setting('app.tenant_id')::uuid);

CREATE POLICY tenant_isolation_can_raw ON can_raw
    USING (tenant_id = current_setting('app.tenant_id')::uuid);

CREATE POLICY tenant_isolation_can_signals ON can_signals
    USING (tenant_id = current_setting('app.tenant_id')::uuid);

CREATE POLICY tenant_isolation_decode_errors ON decode_errors
    USING (tenant_id = current_setting('app.tenant_id')::uuid);

-- Create functions for tenant management
CREATE OR REPLACE FUNCTION set_tenant_context(tenant_uuid UUID)
RETURNS VOID AS $$
BEGIN
    PERFORM set_config('app.tenant_id', tenant_uuid::text, true);
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION get_tenant_context()
RETURNS UUID AS $$
BEGIN
    RETURN current_setting('app.tenant_id')::uuid;
END;
$$ LANGUAGE plpgsql;

-- Create function to update tenant usage
CREATE OR REPLACE FUNCTION update_tenant_usage(
    p_tenant_id UUID,
    p_date DATE,
    p_frames_received BIGINT DEFAULT 0,
    p_frames_processed BIGINT DEFAULT 0,
    p_can_frames_received BIGINT DEFAULT 0,
    p_can_signals_decoded BIGINT DEFAULT 0,
    p_api_requests BIGINT DEFAULT 0,
    p_storage_bytes BIGINT DEFAULT 0
)
RETURNS VOID AS $$
BEGIN
    INSERT INTO tenant_usage (
        tenant_id, date, frames_received, frames_processed,
        can_frames_received, can_signals_decoded, api_requests, storage_bytes
    )
    VALUES (
        p_tenant_id, p_date, p_frames_received, p_frames_processed,
        p_can_frames_received, p_can_signals_decoded, p_api_requests, p_storage_bytes
    )
    ON CONFLICT (tenant_id, date)
    DO UPDATE SET
        frames_received = tenant_usage.frames_received + p_frames_received,
        frames_processed = tenant_usage.frames_processed + p_frames_processed,
        can_frames_received = tenant_usage.can_frames_received + p_can_frames_received,
        can_signals_decoded = tenant_usage.can_signals_decoded + p_can_signals_decoded,
        api_requests = tenant_usage.api_requests + p_api_requests,
        storage_bytes = tenant_usage.storage_bytes + p_storage_bytes,
        updated_at = NOW();
END;
$$ LANGUAGE plpgsql;

-- Create function to check tenant quotas
CREATE OR REPLACE FUNCTION check_tenant_quota(
    p_tenant_id UUID,
    p_quota_type VARCHAR(100),
    p_quota_usage BIGINT
)
RETURNS BOOLEAN AS $$
DECLARE
    quota_limit BIGINT;
    quota_used BIGINT;
BEGIN
    SELECT quota_limit, quota_used
    INTO quota_limit, quota_used
    FROM tenant_quotas
    WHERE tenant_id = p_tenant_id AND quota_type = p_quota_type;
    
    IF quota_limit IS NULL THEN
        RETURN TRUE; -- No quota set, allow
    END IF;
    
    RETURN (quota_used + p_quota_usage) <= quota_limit;
END;
$$ LANGUAGE plpgsql;

-- Create function to update tenant quota usage
CREATE OR REPLACE FUNCTION update_tenant_quota(
    p_tenant_id UUID,
    p_quota_type VARCHAR(100),
    p_quota_usage BIGINT
)
RETURNS VOID AS $$
BEGIN
    INSERT INTO tenant_quotas (tenant_id, quota_type, quota_limit, quota_used)
    VALUES (p_tenant_id, p_quota_type, 0, p_quota_usage)
    ON CONFLICT (tenant_id, quota_type)
    DO UPDATE SET
        quota_used = tenant_quotas.quota_used + p_quota_usage,
        updated_at = NOW();
END;
$$ LANGUAGE plpgsql;

-- Create triggers for automatic tenant context setting
CREATE OR REPLACE FUNCTION trigger_set_tenant_context()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.tenant_id IS NOT NULL THEN
        PERFORM set_config('app.tenant_id', NEW.tenant_id::text, true);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_tenant_api_keys_tenant_id ON tenant_api_keys(tenant_id);
CREATE INDEX IF NOT EXISTS idx_tenant_api_keys_api_key ON tenant_api_keys(api_key);
CREATE INDEX IF NOT EXISTS idx_tenant_devices_tenant_id ON tenant_devices(tenant_id);
CREATE INDEX IF NOT EXISTS idx_tenant_devices_device_id ON tenant_devices(device_id);
CREATE INDEX IF NOT EXISTS idx_tenant_usage_tenant_date ON tenant_usage(tenant_id, date);
CREATE INDEX IF NOT EXISTS idx_tenant_quotas_tenant_type ON tenant_quotas(tenant_id, quota_type);
CREATE INDEX IF NOT EXISTS idx_tenant_billing_tenant_period ON tenant_billing(tenant_id, billing_period_start, billing_period_end);

-- Insert default tenant for existing data
INSERT INTO tenants (id, name, slug, description, status)
VALUES (
    '00000000-0000-0000-0000-000000000000',
    'Default Tenant',
    'default',
    'Default tenant for existing data',
    'active'
)
ON CONFLICT (slug) DO NOTHING;

-- Update existing data to use default tenant
UPDATE raw_frames SET tenant_id = '00000000-0000-0000-0000-000000000000' WHERE tenant_id IS NULL;
UPDATE telemetry_flat SET tenant_id = '00000000-0000-0000-0000-000000000000' WHERE tenant_id IS NULL;
UPDATE decode_errors SET tenant_id = '00000000-0000-0000-0000-000000000000' WHERE tenant_id IS NULL;
UPDATE can_raw SET tenant_id = '00000000-0000-0000-0000-000000000000' WHERE tenant_id IS NULL;
UPDATE can_signals SET tenant_id = '00000000-0000-0000-0000-000000000000' WHERE tenant_id IS NULL;

