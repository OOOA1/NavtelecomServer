-- Создание базы данных и пользователя
CREATE DATABASE navtelecom_server;
CREATE USER navtelecom WITH PASSWORD 'password';
GRANT ALL PRIVILEGES ON DATABASE navtelecom_server TO navtelecom;

-- Подключение к базе данных
\c navtelecom_server;

-- Таблица устройств
CREATE TABLE devices (
    id SERIAL PRIMARY KEY,
    unique_id VARCHAR(50) UNIQUE NOT NULL,
    imei VARCHAR(15) UNIQUE,
    name VARCHAR(255),
    model VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_seen TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN DEFAULT TRUE
);

-- Таблица позиций GPS
CREATE TABLE positions (
    id SERIAL PRIMARY KEY,
    device_id INTEGER REFERENCES devices(id) ON DELETE CASCADE,
    unique_id VARCHAR(50) NOT NULL,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    speed DOUBLE PRECISION,
    course DOUBLE PRECISION,
    altitude DOUBLE PRECISION,
    satellites INTEGER,
    hdop DOUBLE PRECISION,
    fix_time TIMESTAMP WITH TIME ZONE NOT NULL,
    server_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    raw_data TEXT
);

-- Таблица сырых кадров
CREATE TABLE raw_frames (
    id SERIAL PRIMARY KEY,
    device_id INTEGER REFERENCES devices(id) ON DELETE CASCADE,
    unique_id VARCHAR(50) NOT NULL,
    frame_type VARCHAR(10) NOT NULL, -- A, T, X, E
    raw_data TEXT NOT NULL,
    parsed_data JSONB,
    received_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Таблица CAN-данных
CREATE TABLE can_data (
    id SERIAL PRIMARY KEY,
    device_id INTEGER REFERENCES devices(id) ON DELETE CASCADE,
    unique_id VARCHAR(50) NOT NULL,
    can_id VARCHAR(10) NOT NULL,
    can_data JSONB NOT NULL,
    position_id INTEGER REFERENCES positions(id) ON DELETE SET NULL,
    received_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Индексы для оптимизации запросов
CREATE INDEX idx_devices_unique_id ON devices(unique_id);
CREATE INDEX idx_devices_imei ON devices(imei);
CREATE INDEX idx_positions_device_id ON positions(device_id);
CREATE INDEX idx_positions_unique_id ON positions(unique_id);
CREATE INDEX idx_positions_fix_time ON positions(fix_time);
CREATE INDEX idx_raw_frames_device_id ON raw_frames(device_id);
CREATE INDEX idx_raw_frames_unique_id ON raw_frames(unique_id);
CREATE INDEX idx_raw_frames_frame_type ON raw_frames(frame_type);
CREATE INDEX idx_can_data_device_id ON can_data(device_id);
CREATE INDEX idx_can_data_unique_id ON can_data(unique_id);
CREATE INDEX idx_can_data_can_id ON can_data(can_id);

-- Функция для обновления updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Триггер для автоматического обновления updated_at
CREATE TRIGGER update_devices_updated_at BEFORE UPDATE ON devices
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

