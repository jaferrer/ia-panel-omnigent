# Plan: `ompr` como harness seleccionable en omnigent (siempre con filtrado OmniRoute)

## Objetivo

`omnigent run --harness ompr` (y cualquier resolución que pase por
`canonicalize_harness("ompr")`) debe lanzar el harness **pi-native** usando como
ejecutable el wrapper `ompr` (`~/.local/bin/ompr`, symlink a
`~/ai/HUB/pi-extensions/bin/ompr`), en vez del CLI `pi`.

Regla dura (usuario, 2026-08-26): **pi-native SIEMPRE ejecuta `ompr`**, también
cuando se pida `--harness pi` o `pi-native` o el subcomando equivalente. El
filtrado de combos `--omniroute --models 'omniroute/*'` solo se aplica pasando
por el wrapper, así que NO hay fallback a `pi` desnudo: si `ompr` no está y no
hay `OMNIGENT_PI_PATH` explícito, falla con mensaje claro de instalación.

(`pir` — wrapper zsh de `pi --omniroute` en `~/.local/bin/pir` — apunta al CLI
pi comercial, no al fork; omnigent NO lo usa. Solo `ompr`.)

Diseño: **no se crea un harness nuevo completo**. Dos cambios:
alias `ompr → pi-native` + ejecutable por defecto de pi-native pasa a ser
`ompr`. Un punto de cambio de comportamiento (`omnigent/pi_native.py`), cero
módulos duplicados.

Repo de trabajo: `/Users/ferrer/ai/HUB/omnigent`. Rutas relativas a esa raíz.

Prerequisito del entorno (ya cumplido hoy, verificar con `which ompr`):
`~/.local/bin/ompr` existe y apunta a `~/ai/HUB/pi-extensions/bin/ompr`.

---

## Paso 1 — Alias `ompr → pi-native`

Fichero: `omnigent/harness_plugins.py`.

Busca el dict `aliases={ ... }` (contiene líneas como `"native-pi": "pi-native",`).
Añade en orden alfabético dentro del dict literal:

```python
        "ompr": "pi-native",
```

Nada más en este fichero. `canonicalize_harness("ompr")` devolverá
`"pi-native"`, y con eso heredan automáticamente:

- `_validate_harness()` en `omnigent/cli.py` (canoniza antes de comprobar
  `OMNIGENT_HARNESSES`).
- `native_coding_agent_for_harness()` en `omnigent/native_coding_agents.py`
  (canoniza antes del lookup → agente `pi` → dispatch `run_pi_native`).
- El módulo inner `omnigent.inner.pi_native_harness` (lookup con id canonizada
  en `harness_modules`).

NO añadas `ompr` a `harness_modules`, `native_harnesses`, `native_agents`,
`install_specs` ni `_OS_ENV_HARNESSES`: reciben siempre la id canonizada.

## Paso 2 — pi-native ejecuta `ompr` siempre

Fichero: `omnigent/pi_native.py`.

1. Localiza la constante `_DEFAULT_PI_COMMAND = "pi"` (zona superior, junto a
   `_PI_PATH_ENV = "OMNIGENT_PI_PATH"`). Cambia su valor a:

```python
_DEFAULT_PI_COMMAND = "ompr"
```

2. En la función `resolve_pi_executable`, localiza el `raise click.ClickException(...)`
   cuyo mensaje habla de que falta el CLI `pi`. Reemplaza el texto del mensaje
   por:

```python
            "Native requires the 'ompr' wrapper on PATH. "
            "Install it with: ln -sf ~/ai/HUB/pi-extensions/bin/ompr ~/.local/bin/ompr "
            "or set OMNIGENT_PI_PATH=/path/to/ompr. "
```

   Mantén el f-string `f"You set {_PI_PATH_ENV}=..."` si existe en el mensaje
   original; no borres otras partes.

3. NO añadas imports ni funciones nuevas. Sobre `pi_version()`/`pi_supports_approve()`:
   no los toques — `ompr --version` pasa los args al fork y devuelve versión,
   así que el gate de `--approve` sigue funcionando.

Precedencia final: `OMNIGENT_PI_PATH` (explícito) → `HARNESS_PI_PATH` (legacy,
con warning) → `ompr`. `pi` desnudo ya no se resuelve nunca como default.

## Paso 3 — Texto de ayuda del CLI

Fichero: `omnigent/cli.py`.

Localiza `_HARNESS_CHOICES_HELP` (línea ~6513, contiene la cadena
`'openai-agents', 'open-responses', 'pi', 'antigravity', ...`). Añade `'ompr'`
inmediatamente después de `'pi',`. Resultado:

```python
    "'openai-agents', 'open-responses', 'pi', 'ompr', 'antigravity', 'qwen', 'goose', 'copilot'"
```

No toques las listas de `click.Choice` de `import` (línea ~5805) ni la lista de
la línea ~1610: tratan sesiones *locales* de herramientas externas, no aplican.

## Paso 4 — Tests

Fichero: `tests/test_harness_aliases.py`. Añade al final:

```python
def test_ompr_alias_resolves_to_pi_native() -> None:
    from omnigent.harness_aliases import canonicalize_harness, is_native_harness, native_terminal_name

    assert canonicalize_harness("ompr") == "pi-native"
    assert is_native_harness("ompr") is True
    assert native_terminal_name("ompr") == "pi"
```

Fichero NUEVO: `tests/test_pi_native_command.py`:

```python
import omnigent.pi_native as pi_native


def test_default_command_is_ompr() -> None:
    assert pi_native._configured_pi_command({}) == "ompr"


def test_env_override_wins() -> None:
    env = {"OMNIGENT_PI_PATH": "/custom/ompr"}
    assert pi_native._configured_pi_command(env) == "/custom/ompr"
```

Antes de dar por hecho el paso, comprueba si hay tests existentes que asuman el
default `"pi"`:

```bash
grep -rn "_DEFAULT_PI_COMMAND\|requires 'pi'\|'pi' CLI" tests/ omnigent/ | grep -v pi_native_command
```

Cada test que rompa por el nuevo default se actualiza su expectativa a `"ompr"`
(mismo test, nuevo literal). No silencies tests con skip.

## Paso 5 — Verificación (obligatoria, en orden)

Desde la raíz del repo omnigent:

1. `which ompr` → `~/.local/bin/ompr`. Si no existe:
   `ln -sf ~/ai/HUB/pi-extensions/bin/ompr ~/.local/bin/ompr`.
2. `python -m pytest tests/test_harness_aliases.py tests/test_pi_native_command.py -q`
   → todos verdes.
3. `python -m pytest tests/test_pi_native_bridge.py tests/test_harness_startup_config.py -q`
   → sin regresiones.
4. Humo real: `omnigent run --harness ompr` debe lanzar la TUI del fork
   oh-my-pi mostrando combos `omniroute/*` en el selector de modelos (si sale
   el catálogo pi sin prefijo `omniroute/`, el filtrado NO se aplicó: fallo).
5. Misma comprobación con `omnigent run --harness pi-native`: también debe salir
   con combos `omniroute/*` (es el punto de la regla dura).
6. Regresión del error: con `PATH=/usr/bin:/bin` y sin `OMNIGENT_PI_PATH`, la
   resolución debe fallar con el mensaje nuevo que menciona `ompr` (verificar
   llamando en Python: `python -c "import omnigent.pi_native as m; m.resolve_pi_executable(env={}, which=lambda c: None)"`
   → debe lanzar ClickException con el texto nuevo).

## No-objetivos

- No crear módulo `ompr_native.py` ni filas propias en `native_agents`.
- No env var `OMNIGENT_OMPR_PATH` nueva; se reutiliza `OMNIGENT_PI_PATH`.
- No tocar `split-window.ts` ni nada del repo `~/ai/HUB/omp`: el fork ya
  detecta `OMPR=1` (el wrapper lo exporta).
- No usar `pir`: apunta al CLI pi comercial, no al fork; sin filtrado de
  catálogo fork (`--models 'omniroute/*'`).


---

# Registro de ejecución (2026-08-26, implementer session)

Pasos 1–5 ejecutados OK. Cambios adicionales al plan encontrados durante el smoke:

1. `omnigent/inner/pi_executor.py::_find_pi_cli` (harness `pi` REPL, no cubierto
   por el plan original) también resolvía `pi` desnudo. Cambiado a
   `shutil.which("ompr")` estricto + mensaje de error actualizado. Regla dura
   ("siempre ompr") cubre ambas rutas pi.

2. Gate `--approve` roto: `ompr --version` reporta la versión del fork
   oh-my-pi (18.0.5 ≥ 0.79.0), así que pi-native pasaba `--approve` y el fork
   moría con "unknown flag". Fix en `omnigent/pi_native.py::pi_supports_approve`:
   si el basename del ejecutable empieza por `ompr` → `False`. Test añadido
   `test_approve_flag_never_for_ompr_wrapper`.

Verificación obtenida:
- 209 tests verdes (test_harness_aliases, test_pi_native_command,
  test_pi_native_bridge, test_harness_startup_config, test_pi_executor).
- `omnigent run --harness ompr` lanzó la TUI del fork (omp v18.0.5) sin el
  error --approve; el footer de modelo muestra un modelo OmniRoute
  (`qwen3-coder-30b-a3b-instr… / omnigent`) = filtrado de combos activo.
- Resolución: `_configured_pi_command({}) == "ompr"`, dispatch
  `native_coding_agent_for_harness("ompr") → pi → run_pi_native`,
  `harness_modules()["pi-native"] == "omnigent.inner.pi_native_harness"`.

3. GUI de selección de harness no listaba Pi: readiness/version gate usaba el
   binario `pi`. `omnigent/onboarding/harness_install.py` spec PI_KEY ahora:
   binary `ompr`, sin `package` npm, `install_command` one-click =
   `bash -c "ln -sf ~/ai/HUB/pi-extensions/bin/ompr ~/.local/bin/ompr"`,
   `install_hint` mismo comando. Tests de test_harness_install.py actualizados
   (pi ya no es npm ni version-bounded). 367 tests verdes en suites tocadas.
   Fallos en test_harness_readiness.py / test_databricks_config.py son
   pre-existentes (reproducen igual en árbol limpio).

4. Combos no salían al elegir Pi en GUI tras reinicio:
   - `omniroute_combo_model_options()` hacía GET /v1/models sin Authorization → 401 → lista vacía.
     Fix: `_omniroute_api_key()` + Bearer header (env o ~/.env), mismo fallback que omniroute-combos.ts.
   - Extensión combos vivía en `~/.pi/agent/extensions`, pero omp/ompr usa `~/.omp/agent/extensions`.
     Fix: symlink `omniroute-combos.ts` + `omniroute-quota.ts` ahí.
   - Server reiniciado con código editable (`uv run omnigent server --background`) y host daemon recreado.
   Verificación: `pi_native_model_options()` → 27 combos (Fable5-WA, GPT5.3-SPARK, …). Tests omniroute 4/4.


5. Web GUI no espejaba el TUI (pensaba en TUI, chat web vacío / paralelo):
   - omp (`oh-my-pi`) carga extensiones con `loadLegacyPiModule`. Un CJS
     `module.exports = function (pi) {...}` se reescribe a ModuleNamespace
     vacío → factory inválida → `session_start` / `message_end` no registran.
   - Sintoma: TUI integrada responde bien; web no recibe
     `external_conversation_item` (solo `resource_event`). Inbox queda con
     `user_message` sin consumir. Manual POST con `agent: "Pi"` sí funciona.
   - Fix: `omnigent/pi_native_bridge.py` emite ESM wrapper
     `omnigent_pi_native_extension.mjs` que hace `createRequire(...)` del
     sibling `.js` y `export default`. `extension_path()` apunta al `.mjs`.
   - Verificación: `loadLegacyPiModule(wrapper.mjs)` → `default: function`.
     Test: `test_write_extension_files_emits_esm_wrapper`.
   - Sesiones viejas siguen con solo `.js` roto: hace falta **sesión nueva**
     tras reiniciar server/host.

---

## Lecciones / anti-errores (no repetir)

### Harness / ejecutable
1. **Siempre `ompr`, nunca `pi` desnudo.** También en
   `omnigent/inner/pi_executor.py::_find_pi_cli`, no solo `pi_native.py`.
2. **No fiarse de `--version` del wrapper.** Fork oh-my-pi reporta `18.x`;
   gate `--approve` (`>=0.79`) se activa y el fork muere. Basename `ompr*`
   → `pi_supports_approve = False`.
3. **Readiness GUI = binario del install spec.** Si `PI_KEY.binary="pi"` y
   PATH solo tiene `ompr`, la fila Pi desaparece. Spec debe gatear `ompr`.

### Combos OmniRoute
4. **`GET /v1/models` exige Bearer desde 2026-08-25.** Sin
   `Authorization: Bearer $OMNIROUTE_API_KEY` → 401 → lista vacía en GUI.
   Mismo fallback que `omniroute-combos.ts`: env o `~/.env`.
5. **omp lee extensiones de `~/.omp/agent/extensions`, no `~/.pi/...`.**
   Symlink ahí `omniroute-combos.ts` + `omniroute-quota.ts`.
6. **`ompr` ya pasa `--omniroute --models omniroute/*`.** La extensión
   combos refuerza; no sustituye auth ni path de extensions omp.

### Mirror GUI↔TUI
7. **Extensiones CJS puras rompen bajo omp.** Emitir siempre ESM
   (`export default`) o wrapper `createRequire`. Probar con:
   `loadLegacyPiModule(path)` → debe dar `typeof default === "function"`.
8. **Tras cambiar bridge/extension: reiniciar server + host y abrir
   sesión NUEVA.** Bridges viejos no se reescriben solos.
9. **Diagnóstico rápido mirror roto:**
   - TUI responde + `sessions/*.jsonl` tiene assistant → TUI OK.
   - `GET /v1/sessions/{id}/items` solo `resource_event` → extensión no posta.
   - Inbox con `user_message` sin consumir → poller no arrancó (`session_start`
     no corrió).
   - POST manual con `agent: "Pi"` 202 → server OK; fallo está en load/ext.

### Runtime / deploy
10. **`~/.local/bin/omnigent` es uv tool; el server vivo puede no ser el
    editable del repo.** Para cambios de código: arrancar con
    `uv run omnigent server --background` desde `~/ai/HUB/omnigent` y
    recrear host (`omnigent host --server http://127.0.0.1:6767 --background`).
11. Fallos preexistentes (no culpar a este trabajo):
    `tests/onboarding/test_harness_readiness.py` (2) y
    `tests/onboarding/test_databricks_config.py` (1).

### Checklist humo mínimo
```bash
which ompr
uv run python -c "from omnigent.pi_native_credentials import pi_native_model_options as f; print(len(f()), f()[:3])"
# → >0 combos
uv run omnigent server status
uv run omnigent host status
# abrir sesión Pi NUEVA desde GUI; TUI responde; chat web espeja texto/thinking
ls ~/.omnigent/pi-native/*/omnigent_pi_native_extension.mjs | tail -1
```

## Modo corporativo contra el gateway del panel (O1)

En despliegues corporativos (`OMNIGENT_OMPR_CORPORATE=1`) el gateway del panel
(`scripts/tui-gateway.ts` de `ia-panel-next-plan`, compatible OpenAI) es la
ÚNICA entrada LLM. El cliente recibe una credencial de dispositivo revocable
(código de emparejamiento `PANEL-xxxx` o `credentialId`) cuyo `/v1/models`
devuelve exactamente los combos de su alcance.

### Variables de entorno

| Variable | Secreta | Cruza host→runner | Descripción |
|---|---|---|---|
| `OMNIGENT_OMPR_CORPORATE` | no | sí | Activa el contrato corporativo fail-closed. |
| `OMNIGENT_OMPR_CATALOG_ENV` | no (ruta) | sí | Ruta al fichero protegido `ompr-catalog.env`. |
| `OMNIGENT_OMPR_GATEWAY_URL` | no | sí | Origen del gateway; fijarla selecciona modo gateway. |
| `OMNIGENT_OMPR_DEFAULT_COMBO` | no | sí | Combo por defecto (regla 3); si no, `colotool-default`. |
| `OMNIGENT_OMPR_GATEWAY_TOKEN` | **sí** | **no** | Credencial de dispositivo (`Authorization: Bearer`). |
| `OMNIROUTE_API_KEY` | **sí** | **no** | Token del catálogo OmniRoute-directo. |

Los secretos solo viven en el fichero protegido que lee el propio runner
(`_ompr_catalog_env_values()`); el fichero gana al entorno de proceso, igual
que `_omniroute_api_key()`. El `env_unset` corporativo de
`orchestration.py` los elimina del hijo `ompr` generado.

### Flujo en modo gateway

1. `ompr_gateway_config()` resuelve `(base_url, token)` o `None` (ruta
   OmniRoute-directa intacta cuando no hay URL).
2. `ompr_catalog_options()` hace `GET {base}/v1/models` con el Bearer y
   convierte `data[].id` en opciones `{id, model, displayName}`.
3. Un 401/403 del gateway lanza `OmprComboCatalogError` con mensaje de
   matriculación (dispositivo no matriculado, código gastado/caducado o
   credencial revocada → re-matricular en el panel). Otros errores de
   red/JSON devuelven `[]`, que aborta vía `select_ompr_corporate_combo`.
4. `select_ompr_corporate_combo()` aplica las 5 reglas con el defecto
   configurable (`_ompr_default_combo()`).
5. `orchestration.py` construye `ompr_gateway_provider(...)` (proveedor
   `openai-completions`, `provider_id="ia-panel"`,
   `base_url="{base}/v1"`, `auth_header=True`, todos los combos
   registrados) y fusiona su `cred_env`/`cred_args` como la rama
   `provider is not None` existente — `--provider ia-panel --model <combo>`,
   nunca `--omniroute`.
6. `pi_native_model_options()` usa `ompr_catalog_options()` en modo
   corporativo: con credencial rechazada el selector queda vacío, nunca el
   fallback del proveedor gestionado.
