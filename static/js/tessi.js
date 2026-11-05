document.addEventListener("DOMContentLoaded", function () {

    const widget = document.getElementById("tessiWidget");

    // Si el usuario no inició sesión, no se ejecuta el chat.
    if (!widget) return;

    const toggle = document.getElementById("tessiToggle");
    const windowChat = document.getElementById("tessiWindow");
    const close = document.getElementById("tessiClose");
    const messages = document.getElementById("tessiMessages");
    const form = document.getElementById("tessiForm");
    const input = document.getElementById("tessiInput");

    // Comprobar que exista toda la estructura del chat.
    if (!toggle || !windowChat || !close || !messages || !form || !input) {
        console.error("TESSI: faltan elementos HTML necesarios.");
        return;
    }

    const nombre = widget.dataset.nombre || "Usuario";
    const rolOriginal = (widget.dataset.rol || "usuario").toLowerCase();

    // Reconocer el rol de la cuenta.
    let rol = rolOriginal;

    if (rolOriginal === "alumno" || rolOriginal === "alumna") {
        rol = "estudiante";
    }

    let iniciado = false;

    // ======================================================
    // MENSAJES
    // ======================================================

    function agregarMensaje(texto, tipo) {

        const mensaje = document.createElement("div");

        mensaje.className = "tessi-message " + tipo;
        mensaje.textContent = texto;

        messages.appendChild(mensaje);
        messages.scrollTop = messages.scrollHeight;
    }

    // ======================================================
    // RESPUESTAS GENERALES SEGÚN EL ROL
    // ======================================================

    const respuestasPorRol = {

        estudiante: {

            entregas: "Puedes enviar tus trabajos desde el detalle de tu investigación. Después de entregar un documento, quedará pendiente de revisión por parte de tu tutor. Si necesitas corregirlo, podrás realizar una nueva entrega cuando corresponda.",

            investigaciones: "En Mis investigaciones puedes consultar las monografías en las que participas, revisar su estado y acceder al detalle de cada proyecto.",

            reuniones: "Puedes consultar las reuniones relacionadas con tu investigación. Cuando tu solicitud sea aceptada y exista un enlace válido, podrás ingresar a la reunión mediante el botón correspondiente.",

            biblioteca: "En la Biblioteca virtual puedes consultar materiales y recursos educativos que te ayudarán a desarrollar tu monografía.",

            catalogo: "En el Catálogo académico puedes explorar investigaciones registradas y consultar información de los trabajos disponibles.",

            grupos: "En la sección de investigaciones puedes consultar la información de tu grupo y los integrantes que participan en la monografía.",

            perfil: "En Mi perfil puedes consultar la información de tu cuenta y los datos registrados en TESIS LAB.",

            notificaciones: "En Notificaciones puedes revisar los avisos sobre tus entregas, investigaciones y otras actividades de la plataforma.",

            ayuda: "Como estudiante, puedo orientarte sobre entregas, investigaciones, grupos, reuniones, biblioteca virtual, catálogo académico, notificaciones y los seis niveles de tu monografía."
        },

        tutor: {

            entregas: "Desde el Centro de revisiones puedes consultar los trabajos pendientes. Ingresa a una entrega para revisar el documento, registrar observaciones y realizar la evaluación correspondiente.",

            investigaciones: "En Mis investigaciones puedes consultar los trabajos relacionados con tu actividad como tutor y acceder al detalle de cada monografía.",

            reuniones: "Puedes consultar las solicitudes de reunión de tus estudiantes y gestionar las respuestas disponibles. También puedes ingresar a las reuniones aceptadas mediante su enlace.",

            biblioteca: "En la Biblioteca virtual puedes consultar los recursos educativos disponibles para orientar a tus estudiantes durante el desarrollo de sus investigaciones.",

            catalogo: "En el Catálogo académico puedes explorar investigaciones registradas y consultar los trabajos que necesitan asignación de tutor, según los permisos de tu cuenta.",

            grupos: "En Grupos a cargo puedes consultar los grupos relacionados con tu actividad como tutor y revisar la información de sus investigaciones.",

            perfil: "En Mi perfil puedes consultar la información de tu cuenta y tus datos registrados en la plataforma.",

            notificaciones: "En Notificaciones puedes consultar los avisos relacionados con entregas, solicitudes de reunión y actividades de tus investigaciones.",

            ayuda: "Como tutor, puedo orientarte sobre revisión de entregas, evaluaciones, observaciones, grupos a cargo, investigaciones, reuniones, biblioteca, catálogo y metodología de investigación."
        },

        admin: {

            entregas: "Puedes consultar las entregas y dar seguimiento a las actividades de investigación desde las secciones habilitadas para tu cuenta. El Centro de revisiones está destinado principalmente a la revisión de los tutores.",

            investigaciones: "Desde la sección Investigaciones puedes consultar los proyectos registrados en TESIS LAB y acceder a sus detalles.",

            reuniones: "Puedes consultar la información de las reuniones disponibles en la plataforma y realizar el seguimiento correspondiente desde las secciones habilitadas.",

            biblioteca: "En la Biblioteca virtual puedes consultar los recursos educativos registrados en la plataforma y revisar su disponibilidad.",

            catalogo: "En el Catálogo académico puedes explorar las investigaciones registradas y consultar su información.",

            grupos: "Puedes consultar la información de los grupos y sus investigaciones desde las secciones de gestión disponibles para tu cuenta.",

            perfil: "En Mi perfil puedes consultar la información de tu cuenta de administrador.",

            notificaciones: "En Notificaciones puedes consultar los avisos generados por las actividades de TESIS LAB.",

            gestion: "Desde la sección Gestión puedes acceder a las funciones administrativas disponibles, como la administración de usuarios y las opciones de gestión de la plataforma.",

            ayuda: "Como administrador, puedo orientarte sobre investigaciones, usuarios, gestión, grupos, reuniones, biblioteca, catálogo y funcionamiento académico de TESIS LAB."
        }

    };

    const respuestas = respuestasPorRol[rol] || respuestasPorRol.estudiante;

    // ======================================================
    // SALUDO PERSONALIZADO
    // ======================================================

    function obtenerSaludo() {

        if (rol === "tutor") {
            return "¡Hola, " + nombre + "! 👋 Soy TESSI, tu asistente de TESIS LAB. Puedo ayudarte con la revisión de entregas, grupos a cargo, investigaciones, reuniones y orientación académica.";
        }

        if (rol === "admin") {
            return "¡Hola, " + nombre + "! 👋 Soy TESSI, tu asistente de TESIS LAB. Puedo orientarte sobre la gestión de la plataforma, investigaciones y metodología académica.";
        }

        return "¡Hola, " + nombre + "! 👋 Soy TESSI, tu asistente de TESIS LAB. Puedo ayudarte a utilizar la plataforma y orientarte en los seis niveles de tu monografía. ¿Qué necesitas saber?";
    }

    // ======================================================
    // ABRIR Y CERRAR EL CHAT
    // ======================================================

    function abrirChat() {

        windowChat.classList.add("open");
        windowChat.setAttribute("aria-hidden", "false");
        toggle.setAttribute("aria-expanded", "true");

        if (!iniciado) {
            agregarMensaje(obtenerSaludo(), "bot");
            iniciado = true;
        }

        input.focus();
    }

    function cerrarChat() {

        windowChat.classList.remove("open");
        windowChat.setAttribute("aria-hidden", "true");
        toggle.setAttribute("aria-expanded", "false");
    }

    toggle.addEventListener("click", function () {

        if (windowChat.classList.contains("open")) {
            cerrarChat();
        } else {
            abrirChat();
        }

    });

    close.addEventListener("click", cerrarChat);

    // ======================================================
    // NORMALIZAR TEXTO
    // ======================================================

    function normalizar(texto) {

        return texto
            .toLowerCase()
            .normalize("NFD")
            .replace(/[\u0300-\u036f]/g, "")
            .replace(/[¿?¡!.,;:()]/g, "")
            .trim();
    }

    // ======================================================
    // BASE DE CONOCIMIENTOS ACADÉMICOS
    // 6 NIVELES · 36 PREGUNTAS
    // ======================================================

    const respuestasAcademicas = [

        // --------------------------------------------------
        // NIVEL 1: PRESENTACIÓN DEL TEMA
        // --------------------------------------------------

        {
            nivel: 1,
            palabras: ["elegir un tema", "como elegir tema", "escoger tema", "seleccionar tema"],
            respuesta: "Para elegir un tema de investigación, busca un asunto que te interese, que sea importante y sobre el cual puedas encontrar información. También debes considerar el tiempo y los recursos disponibles.\n\nEjemplo: estudiar la influencia del uso de redes sociales en el rendimiento académico de los estudiantes."
        },

        {
            nivel: 1,
            palabras: ["delimitar el tema", "delimitacion del tema", "delimitar mi investigacion"],
            respuesta: "Delimitar un tema significa establecer exactamente qué investigarás, a quiénes estudiarás, dónde realizarás la investigación y durante qué periodo.\n\nEjemplo: analizar la influencia del uso de redes sociales en el rendimiento académico de los estudiantes de quinto de secundaria de La Salle Tarija durante la gestión 2026."
        },

        {
            nivel: 1,
            palabras: ["redactar el titulo", "titulo de investigacion", "como hacer el titulo", "titulo de mi monografia"],
            respuesta: "El título debe ser claro, específico y representar el contenido de tu investigación. Evita títulos demasiado extensos o generales.\n\nEjemplo: «Influencia del uso de las redes sociales en el rendimiento académico de los estudiantes de quinto de secundaria»."
        },

        {
            nivel: 1,
            palabras: ["que es la justificacion", "justificacion del tema", "importancia de la investigacion"],
            respuesta: "La justificación explica por qué es importante realizar la investigación. Debes señalar qué beneficios tendrá, quiénes se beneficiarán y qué aporte puede generar.\n\nPuedes considerar la importancia social, educativa, práctica y teórica del estudio."
        },

        {
            nivel: 1,
            palabras: ["identificar un problema", "problema de investigacion", "como encontrar un problema"],
            respuesta: "Un problema de investigación es una situación que necesita ser estudiada o comprendida. Para identificarlo, observa una situación real y pregúntate qué ocurre, a quiénes afecta, dónde sucede y por qué merece investigarse.\n\nProcura respaldar el problema con observaciones o información verificable."
        },

        {
            nivel: 1,
            palabras: ["presentacion del tema", "que es la presentacion", "introduccion del tema"],
            respuesta: "La presentación del tema es una explicación inicial de aquello que investigarás. Debe introducir el tema, ofrecer un contexto, explicar su importancia y anticipar brevemente qué se estudiará.\n\nSu propósito es que el lector comprenda de qué trata tu monografía."
        },

        // --------------------------------------------------
        // NIVEL 2: PLANTEAMIENTO DEL PROBLEMA
        // --------------------------------------------------

        {
            nivel: 2,
            palabras: ["planteamiento del problema", "como plantear el problema", "redactar el problema"],
            respuesta: "Para redactar el planteamiento del problema, comienza explicando la situación general y avanza hacia el problema específico de tu investigación.\n\nDescribe qué sucede, cuáles podrían ser sus causas y qué consecuencias genera. Utiliza información que permita comprender que el problema existe."
        },

        {
            nivel: 2,
            palabras: ["pregunta de investigacion", "formular la pregunta", "pregunta principal"],
            respuesta: "La pregunta de investigación expresa aquello que deseas responder mediante tu estudio. Debe ser clara, específica y estar relacionada directamente con el problema.\n\nEjemplo: ¿Cómo influye el uso de las redes sociales en el rendimiento académico de los estudiantes de quinto de secundaria?"
        },

        {
            nivel: 2,
            palabras: ["objetivo general", "redactar objetivo general", "como hacer el objetivo general"],
            respuesta: "El objetivo general expresa el propósito principal de la investigación. Generalmente comienza con un verbo en infinitivo, como analizar, determinar, identificar o describir.\n\nEjemplo: Analizar la influencia del uso de las redes sociales en el rendimiento académico de los estudiantes de quinto de secundaria."
        },

        {
            nivel: 2,
            palabras: ["objetivos especificos", "objetivo especifico", "redactar objetivos especificos"],
            respuesta: "Los objetivos específicos son acciones concretas que permiten alcanzar el objetivo general. Deben estar ordenados y ser posibles de cumplir.\n\nEjemplo:\n1. Identificar los hábitos de uso de redes sociales.\n2. Describir el rendimiento académico de los estudiantes.\n3. Relacionar el uso de redes sociales con el rendimiento académico."
        },

        {
            nivel: 2,
            palabras: ["justificacion del problema", "justificar la investigacion", "por que realizar la investigacion"],
            respuesta: "Para justificar tu investigación debes explicar por qué vale la pena realizarla, cuál es su importancia y qué beneficios puede producir.\n\nIdentifica quiénes serán los beneficiarios y qué aporte ofrecerá tu trabajo. Evita limitarte a decir que el tema es interesante."
        },

        {
            nivel: 2,
            palabras: ["delimitaciones", "delimitacion espacial", "delimitacion temporal", "delimitacion tematica"],
            respuesta: "Las delimitaciones establecen los límites de tu investigación.\n\n• Espacial: dónde se realizará.\n• Temporal: durante qué periodo.\n• Temática: qué aspecto específico estudiarás.\n• Poblacional: a quiénes estará dirigida.\n\nEstas delimitaciones ayudan a mantener un trabajo concreto y realizable."
        },

        // --------------------------------------------------
        // NIVEL 3: MARCO TEÓRICO
        // --------------------------------------------------

        {
            nivel: 3,
            palabras: ["marco teorico", "que es el marco teorico", "elaborar marco teorico"],
            respuesta: "El marco teórico reúne los conceptos, teorías y estudios anteriores que permiten comprender tu tema de investigación.\n\nPara elaborarlo, organiza la información por temas y subtítulos, utiliza fuentes confiables y explica cómo cada concepto se relaciona con tu problema de investigación."
        },

        {
            nivel: 3,
            palabras: ["antecedentes", "antecedentes de investigacion", "buscar antecedentes"],
            respuesta: "Los antecedentes son investigaciones anteriores relacionadas con tu tema. Puedes buscarlos en repositorios universitarios, revistas científicas y bibliotecas digitales.\n\nDe cada antecedente identifica al autor, año, título, objetivo, metodología y resultados principales. Explica también cómo se relaciona con tu investigación."
        },

        {
            nivel: 3,
            palabras: ["fundamentos teoricos", "bases teoricas", "fundamentacion teorica"],
            respuesta: "Los fundamentos teóricos explican las teorías y conceptos que respaldan tu investigación.\n\nOrganiza la información mediante subtítulos, utiliza fuentes confiables y no te limites a copiar definiciones. Explica las ideas con tus propias palabras y relaciónalas con el problema que estás estudiando."
        },

        {
            nivel: 3,
            palabras: ["citar un libro", "como cito un libro", "cita de libro", "referencia de un libro", "citar libro apa"],
            respuesta: "En APA 7, una cita de libro dentro del texto puede escribirse así:\n\nCita parafraseada: (Pérez, 2021).\nCita textual: (Pérez, 2021, p. 35).\n\nEn la lista de referencias:\nPérez, J. (2021). Título del libro. Editorial.\n\nRecuerda que debes utilizar los datos reales del libro que consultaste."
        },

        {
            nivel: 3,
            palabras: ["citar una pagina web", "citar pagina web", "referencia de internet", "citar sitio web", "cita de internet"],
            respuesta: "En APA 7, una referencia de una página web suele organizarse así:\n\nApellido, N. (Año, día de mes). Título de la página. Nombre del sitio. URL\n\nSi no existe un autor personal, puedes utilizar el nombre de la institución responsable. Comprueba siempre quién publicó la información y cuándo."
        },

        {
            nivel: 3,
            palabras: ["plagio", "evitar plagio", "que es el plagio", "copiar y pegar"],
            respuesta: "El plagio consiste en presentar ideas o textos de otras personas como si fueran propios.\n\nPara evitarlo:\n• Explica las ideas con tus propias palabras.\n• Cita las fuentes que consultaste.\n• Utiliza comillas cuando reproduzcas palabras textuales.\n• Incluye todas las fuentes citadas en las referencias bibliográficas.\n\nParafrasear también requiere citar al autor original."
        },

        // --------------------------------------------------
        // NIVEL 4: MARCO METODOLÓGICO
        // --------------------------------------------------

        {
            nivel: 4,
            palabras: ["enfoque cuantitativo", "enfoque cualitativo", "cuantitativo y cualitativo", "enfoque mixto"],
            respuesta: "Los enfoques de investigación se diferencian por la forma de estudiar el problema.\n\n• Cuantitativo: trabaja con datos numéricos y análisis estadístico.\n• Cualitativo: estudia experiencias, opiniones y significados.\n• Mixto: combina información cuantitativa y cualitativa.\n\nLa elección depende de tus objetivos y de la información que necesitas obtener."
        },

        {
            nivel: 4,
            palabras: ["tipo de investigacion", "tipos de investigacion", "investigacion exploratoria", "investigacion descriptiva", "correlacional", "explicativa"],
            respuesta: "El tipo de investigación depende del propósito del estudio.\n\n• Exploratoria: examina un tema poco estudiado.\n• Descriptiva: caracteriza una situación o fenómeno.\n• Correlacional: estudia la relación entre variables.\n• Explicativa: busca comprender causas y efectos.\n\nSelecciona el tipo que corresponda a lo que realmente pretendes investigar."
        },

        {
            nivel: 4,
            palabras: ["poblacion y muestra", "que es la poblacion", "que es la muestra", "calcular la muestra"],
            respuesta: "La población es el conjunto total de personas o elementos que cumplen las características de tu estudio. La muestra es una parte seleccionada de esa población.\n\nEjemplo: si existen 120 estudiantes en la población y seleccionas 40 para responder una encuesta, los 120 forman la población y los 40 la muestra."
        },

        {
            nivel: 4,
            palabras: ["tecnicas e instrumentos", "tecnica e instrumento", "instrumentos de investigacion", "tecnicas de investigacion"],
            respuesta: "Las técnicas son los procedimientos utilizados para obtener información, mientras que los instrumentos son las herramientas para recogerla.\n\nEjemplos:\n• Técnica: encuesta. Instrumento: cuestionario.\n• Técnica: entrevista. Instrumento: guía de entrevista.\n• Técnica: observación. Instrumento: ficha de observación."
        },

        {
            nivel: 4,
            palabras: ["elaborar una encuesta", "hacer una encuesta", "preguntas de encuesta", "como hacer encuesta"],
            respuesta: "Para elaborar una encuesta, primero define qué información necesitas obtener. Después redacta preguntas claras, breves y relacionadas con tus objetivos.\n\nEvita preguntas que sugieran una respuesta. Incluye instrucciones y opciones de respuesta comprensibles para los participantes."
        },

        {
            nivel: 4,
            palabras: ["validar instrumentos", "validacion de instrumentos", "validar una encuesta", "validacion del cuestionario"],
            respuesta: "La validación de un instrumento permite revisar si sus preguntas son claras, pertinentes y coherentes con los objetivos de la investigación.\n\nPuedes solicitar la revisión de tu docente o de un especialista. Registra las observaciones recibidas y los cambios realizados antes de aplicar el instrumento."
        },

        // --------------------------------------------------
        // NIVEL 5: ANÁLISIS DE RESULTADOS
        // --------------------------------------------------

        {
            nivel: 5,
            palabras: ["organizar datos", "organizar resultados", "ordenar datos de encuesta", "procesar encuestas"],
            respuesta: "Para organizar los datos de una encuesta:\n\n1. Revisa todas las respuestas.\n2. Clasifica la información por pregunta.\n3. Cuenta las respuestas de cada opción.\n4. Organiza los resultados en tablas.\n5. Calcula las frecuencias y porcentajes cuando corresponda.\n\nAsí podrás analizar la información de manera ordenada."
        },

        {
            nivel: 5,
            palabras: ["tablas y graficos", "elaborar graficos", "hacer graficos", "presentar resultados en graficos"],
            respuesta: "Las tablas y gráficos permiten presentar los resultados de manera comprensible.\n\nUtiliza títulos claros, categorías identificables y cantidades correctas. Puedes emplear gráficos de barras, circulares o de líneas, dependiendo del tipo de información.\n\nNo olvides identificar qué representa cada dato."
        },

        {
            nivel: 5,
            palabras: ["calcular porcentajes", "como calcular porcentaje", "sacar porcentaje", "formula del porcentaje"],
            respuesta: "Para calcular un porcentaje utiliza esta fórmula:\n\nPorcentaje = (cantidad / total) × 100\n\nEjemplo: si 20 de 40 estudiantes eligieron una opción:\n(20 / 40) × 100 = 50 %.\n\nEsto significa que la mitad de los estudiantes seleccionó esa respuesta."
        },

        {
            nivel: 5,
            palabras: ["analizar resultados", "analisis de resultados", "interpretar resultados"],
            respuesta: "Analizar resultados significa explicar qué muestran los datos obtenidos y qué significado tienen para tu investigación.\n\nIdentifica tendencias, respuestas frecuentes y diferencias importantes. Después relaciona esos hallazgos con el problema y los objetivos de tu trabajo.\n\nNo te limites a repetir los números: explica qué significan."
        },

        {
            nivel: 5,
            palabras: ["relacionar resultados con objetivos", "resultados y objetivos", "cumplimiento de objetivos"],
            respuesta: "Para relacionar los resultados con los objetivos, revisa cada objetivo específico y determina qué datos permiten responderlo.\n\nPuedes organizar el análisis objetivo por objetivo, presentando las evidencias obtenidas y explicando qué descubriste. Finalmente, integra esos resultados para responder al objetivo general."
        },

        {
            nivel: 5,
            palabras: ["interpretar un grafico", "explicar un grafico", "debajo del grafico", "interpretacion del grafico"],
            respuesta: "Después de presentar un gráfico debes escribir una interpretación.\n\nExplica cuál es el resultado más importante, qué tendencia observas y qué significa para tu investigación.\n\nNo basta con repetir los porcentajes: debes explicar qué revelan los datos y cómo se relacionan con el problema estudiado."
        },

        // --------------------------------------------------
        // NIVEL 6: CONCLUSIONES Y RECOMENDACIONES
        // --------------------------------------------------

        {
            nivel: 6,
            palabras: ["redactar conclusiones", "como hacer conclusiones", "que son las conclusiones", "conclusion de investigacion"],
            respuesta: "Las conclusiones presentan los principales hallazgos de tu investigación.\n\nDeben responder al objetivo general y a los objetivos específicos, resumir lo que descubriste y basarse en los resultados obtenidos.\n\nNo incluyas información nueva que no haya sido estudiada anteriormente."
        },

        {
            nivel: 6,
            palabras: ["responder los objetivos", "conclusiones por objetivos", "cumplir los objetivos"],
            respuesta: "Para responder los objetivos, revisa qué buscabas conseguir con cada uno y explica qué descubriste mediante los resultados.\n\nPuedes redactar una conclusión relacionada con cada objetivo específico. Después integra esos hallazgos para responder el objetivo general de tu investigación."
        },

        {
            nivel: 6,
            palabras: ["redactar recomendaciones", "como hacer recomendaciones", "que son las recomendaciones"],
            respuesta: "Las recomendaciones proponen acciones concretas a partir de los resultados y conclusiones de tu investigación.\n\nDeben ser realistas, útiles y estar relacionadas con el problema estudiado. Puedes indicar quién debería realizar cada acción y qué cambio se espera conseguir."
        },

        {
            nivel: 6,
            palabras: ["presentacion final", "defensa de monografia", "exponer mi investigacion", "exposicion final"],
            respuesta: "Para presentar tu investigación final, organiza tu exposición en este orden:\n\n1. Presentación del problema.\n2. Objetivos.\n3. Marco teórico y metodología.\n4. Resultados principales.\n5. Conclusiones.\n6. Recomendaciones.\n\nUtiliza diapositivas claras, evita leer todo el contenido y prepárate para responder preguntas."
        },

        {
            nivel: 6,
            palabras: ["referencias bibliograficas", "bibliografia final", "lista de referencias", "ordenar referencias", "referencias apa"],
            respuesta: "En la lista de referencias debes incluir todas las fuentes que citaste en tu monografía.\n\nEn APA 7 revisa que los autores, fechas, títulos y datos de publicación estén completos. Ordena las referencias alfabéticamente por el apellido del autor y comprueba que cada cita del texto tenga su referencia correspondiente."
        },

        {
            nivel: 6,
            palabras: ["errores de la monografia", "errores que debo evitar", "errores en la investigacion", "errores de investigacion"],
            respuesta: "Al finalizar tu monografía evita estos errores:\n\n• Presentar conclusiones sin evidencias.\n• Dejar objetivos sin responder.\n• Utilizar fuentes sin citarlas.\n• Tener errores de ortografía.\n• Incluir gráficos sin interpretación.\n• Agregar información que no se relaciona con el tema.\n• Ignorar las observaciones del tutor.\n\nRealiza una revisión completa antes de entregar."
        }

    ];

    // ======================================================
    // BUSCAR RESPUESTAS ACADÉMICAS
    // ======================================================

    function buscarRespuestaAcademica(consulta) {

        let mejorCoincidencia = null;
        let mejorPuntuacion = 0;

        respuestasAcademicas.forEach(function (item) {

            let puntuacion = 0;

            item.palabras.forEach(function (palabra) {

                const termino = normalizar(palabra);

                if (consulta.includes(termino)) {

                    // Las expresiones más específicas tienen más peso.
                    puntuacion += termino.length + 5;
                }

            });

            if (puntuacion > mejorPuntuacion) {
                mejorPuntuacion = puntuacion;
                mejorCoincidencia = item;
            }

        });

        if (mejorCoincidencia) {

            return "📘 NIVEL " + mejorCoincidencia.nivel +
                " · ORIENTACIÓN ACADÉMICA\n\n" +
                mejorCoincidencia.respuesta;
        }

        return null;
    }

    // ======================================================
    // BUSCAR RESPUESTAS GENERALES DE TESIS LAB
    // ======================================================

    function buscarRespuestaGeneral(consulta) {

        if (
            consulta.includes("administrar usuario") ||
            consulta.includes("gestion de usuarios") ||
            consulta.includes("crear usuario") ||
            consulta.includes("administracion") ||
            consulta.includes("permisos")
        ) {

            if (rol === "admin") {
                return respuestas.gestion;
            }

            return "La gestión de usuarios y permisos corresponde a las funciones administrativas de la plataforma.";
        }

        if (
            consulta.includes("entrega") ||
            consulta.includes("revision") ||
            consulta.includes("revisar") ||
            consulta.includes("correccion") ||
            consulta.includes("evaluar") ||
            consulta.includes("calificacion") ||
            consulta.includes("nota")
        ) {
            return respuestas.entregas;
        }

        if (
            consulta.includes("reunion") ||
            consulta.includes("meet") ||
            consulta.includes("videollamada")
        ) {
            return respuestas.reuniones;
        }

        if (
            consulta.includes("biblioteca") ||
            consulta.includes("libro") ||
            consulta.includes("recurso")
        ) {
            return respuestas.biblioteca;
        }

        if (consulta.includes("catalogo")) {
            return respuestas.catalogo;
        }

        if (
            consulta.includes("grupo") ||
            consulta.includes("miembros") ||
            consulta.includes("integrantes")
        ) {
            return respuestas.grupos;
        }

        if (
            consulta.includes("notificacion") ||
            consulta.includes("aviso")
        ) {
            return respuestas.notificaciones;
        }

        if (
            consulta.includes("perfil") ||
            consulta.includes("cuenta")
        ) {
            return respuestas.perfil;
        }

        if (
            consulta.includes("investigacion") ||
            consulta.includes("monografia") ||
            consulta.includes("trabajo")
        ) {
            return respuestas.investigaciones;
        }

        if (
            consulta.includes("ayuda") ||
            consulta.includes("que puedes hacer") ||
            consulta.includes("que haces")
        ) {
            return respuestas.ayuda;
        }

        return null;
    }

    // ======================================================
    // MOTOR PRINCIPAL DE TESSI
    // ======================================================

    function buscarRespuesta(texto) {

        const consulta = normalizar(texto);

        if (!consulta) {
            return "Escribe tu consulta y con gusto te ayudaré. 😊";
        }

        // Saludos.
        if (
            consulta === "hola" ||
            consulta.includes("buen dia") ||
            consulta.includes("buenas tardes") ||
            consulta.includes("buenas noches") ||
            consulta === "buenas"
        ) {
            return obtenerSaludo();
        }

        // Agradecimientos.
        if (
            consulta.includes("gracias") ||
            consulta.includes("muchas gracias")
        ) {
            return "¡Con mucho gusto! 😊 Estoy aquí para ayudarte con TESIS LAB y con el desarrollo de tu monografía.";
        }

        // Primero se buscan las respuestas académicas.
        const respuestaAcademica = buscarRespuestaAcademica(consulta);

        if (respuestaAcademica) {
            return respuestaAcademica;
        }

        // Después se buscan las respuestas de la plataforma.
        const respuestaGeneral = buscarRespuestaGeneral(consulta);

        if (respuestaGeneral) {
            return respuestaGeneral;
        }

        // Respuesta cuando no se reconoce la consulta.
        return "Todavía no encuentro una respuesta específica para esa consulta. 😊\n\nPuedes preguntarme sobre:\n\n📚 Investigación: tema, problema, objetivos y justificación.\n📖 Marco teórico: antecedentes, teorías y citas APA 7.\n📊 Metodología: enfoques, población, muestra y encuestas.\n📈 Resultados: tablas, gráficos y porcentajes.\n🎓 Conclusiones y recomendaciones.\n\nTambién puedo orientarte sobre entregas, grupos, reuniones, biblioteca y otras funciones de TESIS LAB.";
    }

    // ======================================================
    // ENVIAR CONSULTAS
    // ======================================================

    function enviarConsulta(texto) {

        const consulta = texto.trim();

        if (!consulta) return;

        agregarMensaje(consulta, "user");

        const respuesta = buscarRespuesta(consulta);

        agregarMensaje(respuesta, "bot");
    }

    // ======================================================
    // FORMULARIO DE MENSAJES
    // ======================================================

    form.addEventListener("submit", function (event) {

        event.preventDefault();

        enviarConsulta(input.value);

        input.value = "";
        input.focus();
    });

    // ======================================================
    // BOTONES DE CONSULTAS FRECUENTES
    // ======================================================

    document.querySelectorAll(".tessi-quick-options button")
        .forEach(function (boton) {

            boton.addEventListener("click", function () {

                const pregunta = boton.dataset.question;
                const respuesta = respuestas[pregunta] || respuestas.ayuda;

                agregarMensaje(boton.textContent.trim(), "user");
                agregarMensaje(respuesta, "bot");

                const url = boton.dataset.url;

                if (url) {

                    const enlace = document.createElement("button");

                    enlace.type = "button";
                    enlace.className = "tessi-send";
                    enlace.style.width = "auto";
                    enlace.style.padding = "8px 12px";
                    enlace.style.marginTop = "5px";
                    enlace.textContent = "Ir a esta sección →";

                    enlace.addEventListener("click", function () {
                        window.location.href = url;
                    });

                    messages.appendChild(enlace);
                    messages.scrollTop = messages.scrollHeight;
                }

            });

        });

    // ======================================================
    // ABRIR TESSI DESDE EL MENÚ LATERAL
    // ======================================================

    document.addEventListener("click", function (event) {

        const enlaceTessi = event.target.closest("#tessiSidebarLink");

        if (!enlaceTessi) return;

        event.preventDefault();

        if (windowChat.classList.contains("open")) {
            cerrarChat();
        } else {
            abrirChat();
        }

    });

});