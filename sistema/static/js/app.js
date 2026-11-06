(function () {
  "use strict";

  // Menú lateral en pantallas pequeñas
  var sidebar = document.getElementById("sidebar");
  var velo = document.getElementById("velo");
  var toggle = document.getElementById("menu-toggle");
  function alternarMenu(abrir) {
    if (!sidebar) return;
    sidebar.classList.toggle("abierto", abrir);
    velo.classList.toggle("activo", abrir);
  }
  if (toggle) toggle.addEventListener("click", function () { alternarMenu(!sidebar.classList.contains("abierto")); });
  if (velo) velo.addEventListener("click", function () { alternarMenu(false); });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") alternarMenu(false); });

  // Notificaciones: se ocultan solas (los errores permanecen más tiempo)
  document.querySelectorAll(".toast").forEach(function (t) {
    var ms = t.classList.contains("toast-error") ? 9000 : 5000;
    setTimeout(function () { t.classList.add("saliendo"); setTimeout(function () { t.remove(); }, 350); }, ms);
  });

  // Ventana de confirmación para formularios con data-confirmar
  var dialogo = document.getElementById("confirmar");
  var pendiente = null;
  document.addEventListener("submit", function (e) {
    var form = e.target;
    if (form.dataset.confirmar && dialogo && typeof dialogo.showModal === "function" && !form.dataset.confirmado) {
      e.preventDefault();
      pendiente = form;
      document.getElementById("confirmar-titulo").textContent = form.dataset.titulo || "¿Confirmas la acción?";
      document.getElementById("confirmar-texto").textContent = form.dataset.confirmar;
      document.getElementById("confirmar-ok").textContent = form.dataset.boton || "Confirmar";
      dialogo.showModal();
      return;
    }
    // Evita doble envío (doble clic o toque repetido)
    if (form.dataset.enviando) { e.preventDefault(); return; }
    form.dataset.enviando = "1";
    form.querySelectorAll("button[type=submit], button:not([type])").forEach(function (b) {
      setTimeout(function () { b.disabled = true; }, 0);
    });
  });
  if (dialogo) dialogo.addEventListener("close", function () {
    if (dialogo.returnValue === "ok" && pendiente) {
      pendiente.dataset.confirmado = "1";
      pendiente.requestSubmit();
    }
    pendiente = null;
  });

  // Mostrar/ocultar contraseña
  document.querySelectorAll("[data-mostrar-clave]").forEach(function (b) {
    b.addEventListener("click", function () {
      var campo = b.parentElement.querySelector("input");
      var visible = campo.type === "text";
      campo.type = visible ? "password" : "text";
      b.textContent = visible ? "Mostrar" : "Ocultar";
    });
  });

  // Copiar contraseña temporal
  document.querySelectorAll("[data-copiar]").forEach(function (b) {
    b.addEventListener("click", function () {
      var texto = document.querySelector(b.dataset.copiar).textContent.trim();
      if (navigator.clipboard) {
        navigator.clipboard.writeText(texto).then(function () { b.textContent = "Copiada"; });
      }
    });
  });

  // Vista previa de imágenes
  var previa = document.getElementById("vista-previa");
  document.querySelectorAll("input[type=file][accept^=image]").forEach(function (input) {
    input.addEventListener("change", function () {
      var archivo = input.files && input.files[0];
      if (!archivo || !previa) return;
      if (archivo.size > 2 * 1024 * 1024) {
        alert("La imagen no puede superar los 2 MB.");
        input.value = "";
        return;
      }
      previa.src = URL.createObjectURL(archivo);
      previa.hidden = false;
    });
  });

  // Tablas: permitir desplazamiento horizontal sin romper el ancho de la página (móvil)
  document.querySelectorAll("table.tabla").forEach(function (tabla) {
    var padre = tabla.parentElement;
    if (padre && padre.classList.contains("tabla-scroll")) return;
    var caja = document.createElement("div");
    caja.className = "tabla-scroll";
    padre.insertBefore(caja, tabla);
    caja.appendChild(tabla);
  });
})();
