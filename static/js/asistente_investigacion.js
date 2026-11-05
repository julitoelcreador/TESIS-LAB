
document.addEventListener("DOMContentLoaded", function () {

    /* ==========================================================
       COMPROBAR ELEMENTOS DEL ASISTENTE
    ========================================================== */

    const selectorCapitulo = document.getElementById("capitulo-select");
    const contenedorPreguntas = document.getElementById("preguntas-guiadas");
    const mensajes = document.getElementById("chat-mensajes");

    // Evitar errores si esta página no contiene el asistente.
    if (!selectorCapitulo || !contenedorPreguntas || !mensajes) {
        return;
    }


    /* ==========================================================
       BASE DE RESPUESTAS POR CAPÍTULO
       6 capítulos con 6 preguntas cada uno.
    ========================================================== */

    const baseRespuestas = [

        // ======================================================
        // NIVEL 1 - PRESENTACIÓN DEL TEMA
        // ======================================================

        [
            {
                pregunta: "¿Cómo elegir un tema de investigación?",
                respuesta: "Para elegir un tema debes identificar una situación que te interese investigar, que tenga importancia y sobre la cual puedas conseguir información. También debes considerar el tiempo y los recursos disponibles.\n\nEjemplo: La influencia de las redes sociales en el rendimiento académico de los estudiantes."
            },
            {
                pregunta: "¿Cómo delimitar el tema?",
                respuesta: "Delimitar significa establecer los límites de tu investigación. Debes precisar qué estudiarás, a quiénes, dónde y durante qué periodo.\n\nEjemplo: La influencia de las redes sociales en estudiantes de quinto de secundaria de La Salle Tarija durante la gestión 2026."
            },
            {
                pregunta: "¿Cómo redactar el título?",
                respuesta: "El título debe ser claro, específico y representar el contenido de tu investigación. Evita títulos demasiado generales o extensos.\n\nEjemplo: Influencia del uso de redes sociales en el rendimiento académico de estudiantes de secundaria."
            },
            {
                pregunta: "¿Qué es la justificación?",
                respuesta: "La justificación explica por qué es importante realizar tu investigación, qué beneficios puede aportar y quiénes podrían beneficiarse de sus resultados.\n\nPuedes explicar su importancia social, educativa, práctica o teórica."
            },
            {
                pregunta: "¿Cómo identificar un problema de investigación?",
                respuesta: "Primero identifica una situación que necesite ser estudiada. Después describe qué sucede, a quién afecta, dónde ocurre y por qué merece investigarse.\n\nEl problema debe poder estudiarse mediante información y evidencias."
            },
            {
                pregunta: "¿Qué es la presentación del tema?",
                respuesta: "Es una explicación inicial de tu investigación. Presenta el tema, su contexto, su importancia y una idea general de lo que desarrollarás en la monografía."
            }
        ],


        // ======================================================
        // NIVEL 2 - CAPÍTULO I: PLANTEAMIENTO DEL PROBLEMA
        // ======================================================

        [
            {
                pregunta: "¿Cómo redactar el planteamiento del problema?",
                respuesta: "Describe la situación que deseas investigar desde un contexto general hasta llegar al problema específico. Explica qué sucede, cuáles son sus posibles causas y qué consecuencias puede tener.\n\nFinaliza dejando clara la situación que tu investigación pretende estudiar."
            },
            {
                pregunta: "¿Cómo formular la pregunta de investigación?",
                respuesta: "La pregunta de investigación debe expresar claramente qué deseas conocer. Debe estar relacionada con tu tema y poder responderse mediante tu investigación.\n\nEjemplo: ¿Cómo influye el uso de redes sociales en el rendimiento académico de los estudiantes de quinto de secundaria?"
            },
            {
                pregunta: "¿Cómo hacer el objetivo general?",
                respuesta: "El objetivo general expresa el propósito principal de tu investigación. Comienza con un verbo en infinitivo como analizar, determinar, identificar o describir.\n\nEjemplo: Analizar la influencia del uso de redes sociales en el rendimiento académico de los estudiantes."
            },
            {
                pregunta: "¿Cómo redactar objetivos específicos?",
                respuesta: "Los objetivos específicos dividen el objetivo general en acciones concretas. Deben ser claros, ordenados y posibles de cumplir.\n\nEjemplo:\n1. Identificar los hábitos de uso de redes sociales.\n2. Describir el rendimiento académico de los estudiantes.\n3. Relacionar los hábitos de uso con el rendimiento académico."
            },
            {
                pregunta: "¿Qué es la justificación?",
                respuesta: "Explica por qué tu investigación merece realizarse. Señala su importancia, los beneficios que puede generar y las personas o grupos que podrían aprovechar sus resultados."
            },
            {
                pregunta: "¿Qué son las delimitaciones?",
                respuesta: "Son los límites que estableces para tu investigación. Pueden ser espaciales (lugar), temporales (periodo), temáticos (contenido) y poblacionales (personas estudiadas)."
            }
        ],


        // ======================================================
        // NIVEL 3 - CAPÍTULO II: MARCO TEÓRICO
        // ======================================================

        [
            {
                pregunta: "¿Qué es el marco teórico?",
                respuesta: "El marco teórico reúne conceptos, teorías y estudios anteriores que ayudan a comprender tu problema de investigación. Sirve como fundamento científico para tu trabajo.\n\nOrganiza la información por temas y subtemas relacionados con tus objetivos."
            },
            {
                pregunta: "¿Cómo buscar antecedentes?",
                respuesta: "Busca investigaciones anteriores relacionadas con tu tema en repositorios universitarios, revistas científicas y bibliotecas digitales.\n\nDe cada antecedente registra el autor, año, título, objetivo, metodología y resultados principales."
            },
            {
                pregunta: "¿Cómo redactar las bases teóricas?",
                respuesta: "Explica los conceptos y teorías que permiten comprender tu tema. Organiza la información con subtítulos, utiliza fuentes confiables y relaciona cada concepto con tu problema de investigación."
            },
            {
                pregunta: "¿Cómo cito un libro en APA 7?",
                respuesta: "Para una cita dentro del texto puedes utilizar el formato: (Pérez, 2021).\n\nEn la lista de referencias:\nPérez, J. (2021). Título del libro. Editorial.\n\nEn una cita textual también debes indicar la página: (Pérez, 2021, p. 35).\n\nRecuerda que el formato exacto depende del tipo de fuente."
            },
            {
                pregunta: "¿Cómo citar una página web?",
                respuesta: "En APA 7, una referencia de una página web generalmente utiliza este formato:\n\nApellido, N. (Año, día de mes). Título de la página. Nombre del sitio. URL\n\nSi no aparece un autor personal, revisa si existe una institución responsable del contenido."
            },
            {
                pregunta: "¿Cómo evitar el plagio?",
                respuesta: "Para evitar el plagio debes reconocer las ideas de otros autores. Parafrasea con tus propias palabras, cita las fuentes y utiliza comillas cuando reproduzcas palabras textuales.\n\nIncluye todas las fuentes utilizadas en tus referencias bibliográficas."
            }
        ],


        // ======================================================
        // NIVEL 4 - CAPÍTULO III: MARCO METODOLÓGICO
        // ======================================================

        [
            {
                pregunta: "¿Qué es el enfoque cuantitativo y cualitativo?",
                respuesta: "El enfoque cuantitativo trabaja principalmente con datos numéricos, mediciones y estadísticas.\n\nEl enfoque cualitativo busca comprender experiencias, opiniones y significados.\n\nTambién existe el enfoque mixto, que combina ambos."
            },
            {
                pregunta: "¿Qué es el tipo de investigación?",
                respuesta: "El tipo de investigación describe el alcance o propósito del estudio. Puede ser exploratorio, descriptivo, correlacional o explicativo, según lo que busques conocer y la profundidad con que estudiarás el problema."
            },
            {
                pregunta: "¿Cómo definir la población y muestra?",
                respuesta: "La población es el conjunto total de personas o elementos que deseas estudiar.\n\nLa muestra es una parte de esa población seleccionada para participar en la investigación.\n\nEjemplo: población: 120 estudiantes; muestra: 40 estudiantes seleccionados para responder una encuesta."
            },
            {
                pregunta: "¿Qué son las técnicas e instrumentos?",
                respuesta: "Las técnicas son procedimientos para obtener información, como la encuesta, entrevista y observación.\n\nLos instrumentos son las herramientas utilizadas para aplicarlas, como cuestionarios, guías de entrevista y fichas de observación."
            },
            {
                pregunta: "¿Cómo elaborar una encuesta?",
                respuesta: "Define qué información necesitas obtener y redacta preguntas claras, breves y relacionadas con tus objetivos. Evita preguntas que sugieran una respuesta.\n\nIncluye instrucciones y opciones de respuesta comprensibles para los participantes."
            },
            {
                pregunta: "¿Cómo validar un instrumento?",
                respuesta: "La validación permite revisar si tu instrumento mide lo que realmente necesitas investigar. Puedes solicitar la revisión de docentes o especialistas para evaluar la claridad, pertinencia y coherencia de las preguntas. Registra las observaciones y los ajustes realizados."
            }
        ],


        // ======================================================
        // NIVEL 5 - CAPÍTULO IV: ANÁLISIS DE RESULTADOS
        // ======================================================

        [
            {
                pregunta: "¿Cómo organizar los datos de una encuesta?",
                respuesta: "Primero revisa todas las respuestas y clasifícalas. Después registra los datos en una tabla, agrupa las respuestas por pregunta y calcula las frecuencias o porcentajes cuando corresponda."
            },
            {
                pregunta: "¿Cómo elaborar tablas y gráficos?",
                respuesta: "Organiza los resultados en tablas con títulos claros, categorías y cantidades. Después puedes representarlos mediante gráficos de barras, sectores o líneas, según el tipo de información.\n\nIndica siempre qué datos representa cada gráfico."
            },
            {
                pregunta: "¿Cómo interpretar porcentajes?",
                respuesta: "Un porcentaje representa una parte de un total de 100. Se calcula así:\n\nPorcentaje = (cantidad / total) × 100.\n\nEjemplo: si 20 de 40 estudiantes responden que sí, el resultado es 50%."
            },
            {
                pregunta: "¿Cómo analizar los resultados?",
                respuesta: "No basta con presentar números. Explica qué muestran los resultados, cuáles son las tendencias más importantes y qué significan en relación con tu problema de investigación y tus objetivos."
            },
            {
                pregunta: "¿Cómo relacionar los resultados con los objetivos?",
                respuesta: "Revisa cada objetivo específico y señala qué resultados ayudan a responderlo. Utiliza los datos recolectados como evidencia y explica si permiten cumplir el objetivo."
            },
            {
                pregunta: "¿Qué debo escribir debajo de un gráfico?",
                respuesta: "Después del gráfico debes incluir una interpretación. Explica cuál es el resultado más importante, qué tendencia observas y qué significa para tu investigación. No repitas simplemente los mismos porcentajes."
            }
        ],


        // ======================================================
        // NIVEL 6 - CAPÍTULO V: CONCLUSIONES Y RECOMENDACIONES
        // ======================================================

        [
            {
                pregunta: "¿Cómo redactar las conclusiones?",
                respuesta: "Las conclusiones presentan los principales hallazgos de tu investigación. Deben responder al objetivo general y a los objetivos específicos, utilizando los resultados obtenidos.\n\nNo agregues datos nuevos que no hayas investigado."
            },
            {
                pregunta: "¿Cómo responder a los objetivos?",
                respuesta: "Revisa cada objetivo específico y explica qué descubriste que permite cumplirlo. Después integra esos resultados para responder al objetivo general."
            },
            {
                pregunta: "¿Cómo elaborar recomendaciones?",
                respuesta: "Las recomendaciones proponen acciones que pueden realizarse a partir de los resultados de tu investigación. Deben ser concretas, realistas y estar relacionadas con las conclusiones."
            },
            {
                pregunta: "¿Cómo presentar los resultados finales?",
                respuesta: "Presenta los resultados más importantes de manera ordenada. Explica el problema, los objetivos, la metodología, los principales hallazgos, las conclusiones y las recomendaciones."
            },
            {
                pregunta: "¿Cómo revisar las referencias bibliográficas?",
                respuesta: "Comprueba que todas las fuentes citadas aparezcan en la lista de referencias y que cada referencia esté correctamente elaborada según APA 7. Revisa autores, fechas, títulos, editoriales y enlaces."
            },
            {
                pregunta: "¿Qué errores debo evitar en mi monografía?",
                respuesta: "Evita conclusiones sin evidencia, objetivos que no se cumplen, citas sin referencias, errores ortográficos, gráficos sin interpretación y apartados que no se relacionan con el tema. Revisa también las observaciones de tu tutor."
            }
        ]

    ];


    /* ==========================================================
       AGREGAR MENSAJES AL CHAT
    ========================================================== */

    function agregarMensaje(texto, tipo) {

        const mensaje = document.createElement("div");

        mensaje.className = "mensaje mensaje-" + tipo;

        mensaje.textContent = texto;

        mensajes.appendChild(mensaje);

        mensajes.scrollTop = mensajes.scrollHeight;

    }


    /* ==========================================================
       CARGAR PREGUNTAS DEL CAPÍTULO SELECCIONADO
    ========================================================== */

    function cargarPreguntas() {

        const indice = Number(selectorCapitulo.value);

        const preguntas = baseRespuestas[indice];

        contenedorPreguntas.innerHTML = "";

        if (!preguntas) {
            return;
        }

        preguntas.forEach(function (item, posicion) {

            const boton = document.createElement("button");

            boton.type = "button";

            boton.className = "respuesta-boton";

            boton.textContent = item.pregunta;

            boton.addEventListener("click", function () {

                consultarPregunta(posicion);

            });

            contenedorPreguntas.appendChild(boton);

        });

    }


    /* ==========================================================
       CONSULTAR RESPUESTA PREDETERMINADA
    ========================================================== */

    function consultarPregunta(posicion) {

        const indice = Number(selectorCapitulo.value);

        const item = baseRespuestas[indice]?.[posicion];

        if (!item) {
            return;
        }

        agregarMensaje(item.pregunta, "usuario");

        agregarMensaje(item.respuesta, "asistente");

    }


    /* ==========================================================
       CAMBIAR CAPÍTULO
    ========================================================== */

    selectorCapitulo.addEventListener("change", function () {

        cargarPreguntas();

        mensajes.innerHTML = "";

        agregarMensaje(
            "Has seleccionado " +
            selectorCapitulo.options[selectorCapitulo.selectedIndex].text +
            ".\n\nSelecciona una de las preguntas disponibles para continuar.",
            "asistente"
        );

    });


    /* ==========================================================
       INICIAR CHAT
    ========================================================== */

    cargarPreguntas();

    agregarMensaje(
        "¡Hola! Soy tu asistente de investigación. Estoy aquí para ayudarte con tu monografía.\n\nSelecciona un capítulo y elige una pregunta para comenzar.",
        "asistente"
    );


    /* ==========================================================
       LISTA DE REVISIÓN
    ========================================================== */

    const checks = document.querySelectorAll(".revision-check");

    function actualizarRevision() {

        const completados = Array.from(checks).filter(
            check => check.checked
        ).length;

        const total = checks.length;

        const faltantes = total - completados;

        const porcentaje = total > 0
            ? Math.round((completados / total) * 100)
            : 0;


        const contador = document.getElementById("revision-contador");

        const porcentajeTexto = document.getElementById("revision-porcentaje");

        const barra = document.getElementById("revision-barra-progreso");

        const aviso = document.getElementById("revision-aviso");


        if (contador) {
            contador.textContent = completados + " de " + total;
        }

        if (porcentajeTexto) {
            porcentajeTexto.textContent = porcentaje + "%";
        }

        if (barra) {
            barra.style.width = porcentaje + "%";
        }

        if (aviso) {

            aviso.textContent = faltantes === 0
                ? "¡Excelente! Completaste todos los puntos de revisión."
                : "Te faltan " + faltantes + " puntos antes de enviar.";

        }

    }


    checks.forEach(function (check) {

        check.addEventListener("change", actualizarRevision);

    });

    actualizarRevision();

});
