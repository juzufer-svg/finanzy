# Supabase: mantenerla activa y respaldarla

Dos tareas automáticas de GitHub Actions (gratis en repositorios públicos):

| Tarea | Archivo | Cuándo corre | Qué hace |
|---|---|---|---|
| Mantener Supabase activo | `.github/workflows/supabase-keepalive.yml` | Lunes y jueves, 8:23 a. m. (Colombia) | Hace una consulta de solo lectura para que Supabase no pause el proyecto por 7 días sin uso |
| Respaldo semanal de Supabase | `.github/workflows/supabase-backup.yml` | Domingos, 3:41 a. m. (Colombia) | Exporta tablas, datos, funciones, triggers y políticas del esquema `public`, los **cifra** con AES-256 y los guarda 90 días como artefacto descargable |

**Por qué cifrado:** el repositorio es público y cualquier usuario de GitHub puede descargar sus
artefactos. El archivo solo se puede abrir con la frase guardada en el secreto `BACKUP_PASSPHRASE`.
El archivo sin cifrar nunca sale del equipo temporal de GitHub y se borra al terminar.

> ⚠️ Si pierdes la frase `BACKUP_PASSPHRASE`, los respaldos no se pueden abrir. Guárdala también
> en tu gestor de contraseñas.

## 1. Secretos que hay que crear (una sola vez)

### `SUPABASE_DB_URL` (cadena de conexión a la base)

1. Supabase → tu proyecto → botón **Connect** (barra superior).
2. Pestaña **Connection String** → tipo **URI** → método **Session pooler**.
   (No uses *Direct connection*: solo funciona por IPv6 y GitHub no lo tiene).
3. Copia la cadena. Tiene la forma
   `postgresql://postgres.<id-proyecto>:[YOUR-PASSWORD]@aws-0-<región>.pooler.supabase.com:5432/postgres`.
4. Reemplaza `[YOUR-PASSWORD]` (con los corchetes) por la contraseña de la base de datos.
   - Si no la recuerdas: **Project Settings → Database → Reset database password**. Usa una
     contraseña de solo letras y números (los símbolos rompen la cadena). Cambiarla **no** afecta
     al backend de Railway, que usa las claves de API (`SUPABASE_KEY`), no esta contraseña.

### `BACKUP_PASSPHRASE` (frase para cifrar los respaldos)

Una frase larga (mínimo 20 caracteres) de **solo letras, números y guiones**, por ejemplo cuatro o
cinco palabras al azar unidas con guiones. Guárdala en tu gestor de contraseñas antes de seguir.

### Dónde se crean en GitHub

GitHub → repositorio `finanzy` → **Settings** → **Secrets and variables** → **Actions** →
pestaña **Secrets** → **New repository secret**. Crea uno por cada secreto con el nombre exacto
(`SUPABASE_DB_URL` y `BACKUP_PASSPHRASE`) y pega el valor → **Add secret**.

## 2. Probar las tareas a mano

GitHub → **Actions** → en la lista de la izquierda elige la tarea → botón **Run workflow** →
rama `main` → **Run workflow**. Espera el círculo verde (1 a 3 minutos).

- **Mantener Supabase activo:** el paso *Consultar la base de datos* debe decir
  "Supabase respondió correctamente".
- **Respaldo semanal de Supabase:** al final de la ejecución, en **Artifacts**, aparece
  `finanzy-respaldo-AAAA-MM-DD.sql.gpg`.

Si una tarea falla, GitHub te envía un correo. El mensaje en rojo del paso dice qué revisar.

## 3. Restaurar un respaldo (PowerShell)

Necesitas `gpg`, que ya viene con **Git para Windows** (`C:\Program Files\Git\usr\bin\gpg.exe`).

### 3.1 Descargar y descifrar

GitHub → **Actions** → **Respaldo semanal de Supabase** → abre la ejecución de la fecha que
quieres → sección **Artifacts** → clic en el nombre para descargar el `.zip`. Luego:

```powershell
cd $HOME\Downloads
$fecha = "2026-11-29"   # cambia por la fecha del respaldo
Expand-Archive ".\finanzy-respaldo-$fecha.sql.gpg.zip" -DestinationPath .\respaldo -Force

$gpg = "C:\Program Files\Git\usr\bin\gpg.exe"
$segura = Read-Host "Frase del respaldo" -AsSecureString
$clave = [System.Net.NetworkCredential]::new('', $segura).Password
$clave | & $gpg --batch --quiet --pinentry-mode loopback --passphrase-fd 0 `
  --output ".\respaldo\finanzy.sql" --decrypt ".\respaldo\finanzy-respaldo-$fecha.sql.gpg"
Remove-Variable clave, segura
```

Si sale `Bad session key`, la frase es incorrecta.

### 3.2 Cargar en Supabase

> ⚠️ Restaurar **reemplaza** las tablas `users`, `categorias`, `transacciones`, `presupuestos`
> y `metas` por el contenido del respaldo. Lo creado después de esa fecha se pierde.
> Si solo quieres revisar el respaldo, cárgalo en un segundo proyecto gratis de Supabase.

1. Abre el archivo: `notepad .\respaldo\finanzy.sql` → **Ctrl+A** → **Ctrl+C**.
2. Supabase → tu proyecto → **SQL Editor** → **New query** → pega (**Ctrl+V**) → **Run**.
   Si Supabase avisa de una operación destructiva, confirma.
3. Comprueba en **Table Editor** que estén tus datos y entra a la app.

### 3.3 Borrar el archivo descifrado

El `.sql` tiene tus datos sin cifrar. Bórralo al terminar:

```powershell
Remove-Item .\respaldo -Recurse -Force
```

## 4. Mantenimiento

- **GitHub desactiva las tareas programadas** de repos públicos tras 60 días sin actividad. La
  tarea de los lunes y jueves las vuelve a habilitar sola. Si aun así recibes el aviso, entra a
  **Actions** → la tarea → **Enable workflow**.
- **Versión de PostgreSQL:** el respaldo usa `pg_dump` 17 (`PG_VERSION` en
  `supabase-backup.yml`). Si Supabase sube tu base a una versión mayor, el respaldo fallará con
  "server version mismatch": cambia `PG_VERSION` a esa versión.
- **Qué no incluye:** cuentas de Supabase Auth, Storage ni tareas `pg_cron` (Finanzy no guarda
  datos ahí; sus usuarios están en la tabla `public.users`).
- **Si cambias la contraseña de la base**, actualiza el secreto `SUPABASE_DB_URL`.
