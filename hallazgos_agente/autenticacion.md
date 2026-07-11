# Hallazgos #12, #13, #14 — Autenticación (ronda de bug-hunting, 2026-07-10)

> Ver `hallazgos_agente/_README_PARA_EL_AGENTE.md` para las reglas de esta carpeta.

**Doc de usuario:** `docs/autenticacion.md` §11
**Estado:** #12 [RESUELTO] 2026-07-10. #13/#14 [RESUELTOS] 2026-07-11.

Contexto: este módulo ya había pasado por una ronda de hardening de seguridad el 2026-07-01 (fix de account-takeover en accept-invite, política de contraseñas, `last_name` NOT NULL — ver `docs/autenticacion.md` §13). Esta es una revisión nueva, posterior, buscando bugs adicionales. Se releyeron enteros: `auth_controller.py`, `auth_service.py`, `auth_schema.py`, `user_schema.py`, y se grepeó `security.py` para tokens/hashing y `limiter`/`Limiter` en todo `app/`.

## Hallazgo #12 — Sin rate limiting en `/auth/login` (ni en el resto de `/auth/*`) — mayor impacto

`grep -rn "limiter\|Limiter" app/` solo devuelve `app/main.py` (donde se instancia `Limiter` y se registra como `app.state.limiter`, más el exception handler) y `web_form_public_controller.py` (donde sí se aplica `@limiter.limit("5/minute")`). **Ningún endpoint de `/auth` tiene el decorador `@limiter.limit(...)`** — ni `/auth/login`, ni `/auth/register`, ni `/auth/refresh`, ni `/auth/change-password`.

El login ya tiene mitigación de timing-attack (hash dummy) para no poder enumerar emails, pero eso no limita la **cantidad** de intentos: un atacante puede probar contraseñas sin límite contra un email conocido (fuerza bruta / credential stuffing), sin bloqueo ni backoff. `main.py` ya tiene toda la infraestructura de `slowapi` montada (se usa en WebForm), así que aplicar el mismo patrón acá es directo.

**Solución recomendada:** agregar `@limiter.limit(...)` a `/auth/login` (ej. `10/minute` por IP, ajustable) y considerar lo mismo para `/auth/register` (protege contra spam de cuentas) y `/auth/refresh`. Si se quiere protección más fuerte que solo por IP, se podría combinar con un límite por email (ej. contador en DB o caché), pero el rate limit por IP ya sería una mejora significativa sobre "ninguno". Test: 11 intentos de login fallido en la misma ventana → el 11vo da `429` en vez de `401`.

## Fix aplicado (2026-07-10)

Alcance acordado con el usuario: `/auth/login` + `/auth/register` (no `/auth/refresh` — requiere poseer un refresh token válido, menor riesgo), `10/minuto` por IP.

`app/controllers/security_controllers/auth_controller.py`: se agregó una instancia propia de `Limiter(key_func=get_remote_address)` a nivel de módulo (mismo patrón que `web_form_public_controller.py` — `slowapi` lee `app.state.limiter`/el exception handler de `RateLimitExceeded`, ya montados en `main.py`), y se decoraron `register`/`login` con `@limiter.limit("10/minute")` (requiere agregar `request: Request` a la firma de ambos endpoints, que es lo que slowapi usa para resolver la IP).

**Efecto colateral de testing importante:** el `Limiter` vive a nivel de módulo (Python), así que sus contadores persisten mientras dure el proceso de `pytest` — no se resetean entre tests. Dos archivos llaman a `/auth/login`/`/auth/register` repetidamente (`test_security_auth.py` y `test_permissions_and_roles.py`); ambos ahora tienen un fixture `autouse=True` que hace `auth_limiter.reset()` antes de cada test, para que la cuota de un test no se filtre a otro y rompa tests sin relación con rate limiting. Mismo patrón ya usado para el rate limit de `WebForm` (ver `hallazgos_agente/formularios_web.md`).

**Test de regresión:** `tests/functional/test_security_auth.py::TestAuthRateLimiting` — 11 intentos de login (credenciales inexistentes) y 11 de register (emails distintos) en la misma ventana → al menos un `429` entre los 11, y el resto de los códigos son los esperados (`401`/`200`) y no otra cosa.

## Hallazgo #13 — Email no se normaliza (case-sensitivity) al registrar/loguear

`AuthService.register` guarda `data.email` tal cual (sin `.lower()`), y `AuthService.login` filtra con `filter_by(email=data.email)` (exacto, sin normalizar). El propio código del módulo demuestra que esto importa: en `_try_join_org_from_invite`, la comparación de emails **sí** se hace con `.strip().lower()` en ambos lados antes de comparar — o sea, hay conciencia de que el case no debería importar, pero no se aplicó de forma consistente en el alta/login.

Consecuencia: alguien podría registrarse con `Test@empresa.com` y luego, si intenta loguearse como `test@empresa.com` (variación de mayúsculas que para un humano es "el mismo email"), el login fallaría (no hay match exacto) — a menos que la collation de Postgres para esa columna sea case-insensitive, lo cual no está confirmado y por default no lo es. También sería posible, en teoría, registrar dos cuentas distintas con el mismo email en distinta capitalización (`Test@x.com` y `test@x.com`), ya que el chequeo de "ya existe" en `register` (`filter_by(email=data.email).first()`) también es exacto.

**Solución recomendada:** normalizar el email a minúsculas (`.strip().lower()`) en un solo lugar antes de guardarlo o compararlo — idealmente en un `field_validator` de `RegisterRequest`/`LoginRequest` (Pydantic), o al menos en `AuthService.register`/`login` antes de las queries. Test: registrar con `Test@x.com`, loguear con `test@x.com` → debe funcionar; intentar registrar `test@x.com` después de `Test@x.com` → debe rechazarse como duplicado.

### Fix aplicado (2026-07-11)

Se agregó `normalize_email(email: str) -> str: return email.strip().lower()` en `app/core/security.py` (misma zona que `validate_password_strength`, comentario cruzado como "única fuente de verdad"). Se aplicó vía `field_validator("email")` en `LoginRequest` y `RegisterRequest` (`auth_schema.py`) y en `UserUpdate` (`user_schema.py`, ver hallazgo #14). No se tocó `InviteRequest.email` — fuera del alcance investigado, el flujo de invitación ya normaliza en el punto de comparación (`_try_join_org_from_invite`/`accept_invite`, ambos con `.strip().lower()` manual).

**Decisión explícita del usuario (2026-07-11) sobre datos ya existentes:** el proyecto todavía está en fase de desarrollo, sin datos reales — solo los generados por los scripts de seed. Por eso el fix es **solo hacia adelante** (normaliza lo que se registra/loguea/actualiza de acá en más); las queries de login/duplicado siguen siendo exact-match (`filter_by(email=...)`), no se agregó `func.lower(User.email)` para cubrir filas que ya pudieran existir con capitalización mixta. Ver la regla general que se dejó anotada en `AGENTS.md` §6 para no volver a preguntar esto en cada hallazgo futuro — si el proyecto pasa a tener datos reales, hay que revisar este criterio.

**Test de regresión:** `tests/functional/test_security_auth.py` — `TestRegister::test_register_normalizes_email_to_lowercase`, `TestRegister::test_register_rejects_duplicate_email_different_case`, `TestLogin::test_login_with_different_case_succeeds_after_register`.

## Hallazgo #14 — `PUT /auth/me`: cambio de email sin validar formato ni unicidad

`UserUpdate.email` (`user_schema.py`) es `Optional[str] = None` — no `EmailStr`, así que no hay validación de formato alguna (acepta cualquier string). Y en `update_me` (`auth_controller.py`), el nuevo valor se asigna directo a `current_user.email` y se hace `db.commit()` sin chequear antes si ese email ya está en uso por otro usuario — la columna `User.email` tiene `unique=True` (`security_models.py:75`), así que una colisión termina en una `IntegrityError` de Postgres sin capturar, que se propaga como `500` genérico en vez de un `400` prolijo.

**Solución recomendada:** (a) cambiar `UserUpdate.email` a `Optional[EmailStr]` para validar formato; (b) en `update_me`, si `data.email` viene y es distinto del actual, chequear explícitamente que no exista otro usuario con ese email (`db.query(User).filter(User.email == data.email, User.id != current_user.id).first()`) y devolver `400` si ya está tomado, antes de hacer el `commit()`. De paso, aplicar la misma normalización de minúsculas del hallazgo #13. Test: dos usuarios existentes, el segundo intenta poner su email igual al del primero vía `PUT /auth/me` → debe dar `400` claro, no `500`.

### Fix aplicado (2026-07-11)

`UserUpdate.email` pasó de `Optional[str]` a `Optional[EmailStr]` (`user_schema.py`), con el mismo `field_validator` de normalización del hallazgo #13 (maneja `None` explícitamente, ya que el campo es opcional). En `update_me` (`auth_controller.py`), antes del loop que asigna los campos: si `data.email is not None` y es distinto del email actual del usuario, se chequea `db.query(User).filter(User.email == data.email, User.id != current_user.id).first()` — si existe, `400` con `"Ese email ya está en uso por otra cuenta."`, antes de tocar `current_user`/hacer `commit()`. La comparación "es distinto del actual" ya usa el email normalizado de ambos lados, así que reenviar el propio email en otra capitalización no dispara el chequeo de unicidad en falso.

**Test de regresión:** `tests/functional/test_security_auth.py::TestUpdateMe` — `test_update_me_rejects_email_taken_by_another_user`, `test_update_me_rejects_invalid_email_format`, `test_update_me_normalizes_new_email`, `test_update_me_allows_resubmitting_own_email_different_case`.
