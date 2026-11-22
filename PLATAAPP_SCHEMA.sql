-- Finanzy — Esquema de referencia de la base de datos (Supabase / PostgreSQL)
-- Sirve para crear una base nueva desde cero. Los cambios sobre la base existente se
-- aplican con las migraciones de backend/sql/ (en orden de fecha).

-- Crear tabla users (si no existe)
CREATE TABLE IF NOT EXISTS users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email VARCHAR(255) UNIQUE NOT NULL,
  hashed_password VARCHAR(255) NOT NULL,
  full_name VARCHAR(255),
  currency VARCHAR(3) DEFAULT 'USD' CHECK (currency IN ('USD', 'EUR', 'MXN', 'ARS', 'COP', 'CLP')),
  is_active BOOLEAN DEFAULT TRUE,
  session_version INTEGER NOT NULL DEFAULT 0,  -- sube al restablecer la contraseña (INV-016)
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

-- Crear tabla categorias
CREATE TABLE IF NOT EXISTS categorias (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  usuario_id UUID REFERENCES users(id) ON DELETE CASCADE NOT NULL,
  nombre VARCHAR(100) NOT NULL,
  icono VARCHAR(10),
  tipo VARCHAR(20) NOT NULL CHECK (tipo IN ('ingreso', 'gasto')),
  created_at TIMESTAMP DEFAULT NOW()
);

-- Crear tabla transacciones
CREATE TABLE IF NOT EXISTS transacciones (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  usuario_id UUID REFERENCES users(id) ON DELETE CASCADE NOT NULL,
  categoria_id UUID REFERENCES categorias(id) ON DELETE SET NULL,
  monto NUMERIC(12,2) NOT NULL,
  descripcion TEXT,
  fecha DATE NOT NULL,
  tipo VARCHAR(20) NOT NULL CHECK (tipo IN ('ingreso', 'gasto')),
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

-- Crear tabla presupuestos
CREATE TABLE IF NOT EXISTS presupuestos (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  usuario_id UUID REFERENCES users(id) ON DELETE CASCADE NOT NULL,
  categoria_id UUID REFERENCES categorias(id) ON DELETE CASCADE NOT NULL,
  limite_mensual NUMERIC(12,2) NOT NULL,
  mes_ano VARCHAR(7) NOT NULL,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

-- Crear tabla metas
CREATE TABLE IF NOT EXISTS metas (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  usuario_id UUID REFERENCES users(id) ON DELETE CASCADE NOT NULL,
  nombre VARCHAR(255) NOT NULL,
  monto_objetivo NUMERIC(12,2) NOT NULL,
  monto_actual NUMERIC(12,2) DEFAULT 0,
  fecha_objetivo DATE NOT NULL,
  estado VARCHAR(20) DEFAULT 'en_progreso' CHECK (estado IN ('en_progreso', 'completada', 'cancelada')),
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

-- Crear índices para mejor rendimiento
CREATE INDEX idx_transacciones_usuario ON transacciones(usuario_id);
CREATE INDEX idx_transacciones_fecha ON transacciones(fecha);
CREATE INDEX idx_categorias_usuario ON categorias(usuario_id);
CREATE INDEX idx_presupuestos_usuario ON presupuestos(usuario_id);
CREATE INDEX idx_presupuestos_mes ON presupuestos(mes_ano);
CREATE INDEX idx_metas_usuario ON metas(usuario_id);

-- Índices para los borrados en cascada por categoría
CREATE INDEX idx_transacciones_categoria ON transacciones(categoria_id);
CREATE INDEX idx_presupuestos_categoria ON presupuestos(categoria_id);

-- Las categorías por defecto las crea el backend para cada usuario la primera vez que las pide
-- (no se insertan aquí: una fila con un usuario inexistente sería un registro huérfano).

-- Crear función para actualizar el campo updated_at automáticamente
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ language 'plpgsql';

-- Crear triggers para updated_at
CREATE TRIGGER update_transacciones_updated_at BEFORE UPDATE ON transacciones
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_presupuestos_updated_at BEFORE UPDATE ON presupuestos
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_metas_updated_at BEFORE UPDATE ON metas
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Habilitar RLS (Row Level Security) si es necesario
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE transacciones ENABLE ROW LEVEL SECURITY;
ALTER TABLE categorias ENABLE ROW LEVEL SECURITY;
ALTER TABLE presupuestos ENABLE ROW LEVEL SECURITY;
ALTER TABLE metas ENABLE ROW LEVEL SECURITY;

-- Sin políticas: el frontend nunca habla con Supabase. Solo el backend accede, con la clave
-- service_role (que no está sujeta a RLS) y verificando el dueño de cada registro (INV-001).
-- Con RLS activo y sin políticas, las claves públicas (anon) no pueden leer ni escribir nada.
