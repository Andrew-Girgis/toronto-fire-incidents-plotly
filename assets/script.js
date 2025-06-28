// Simple fade-in for the whole page
document.addEventListener("DOMContentLoaded", function () {
    document.body.style.opacity = 0;
    requestAnimationFrame(() => {
      document.body.style.transition = "opacity 600ms ease";
      document.body.style.opacity = 1;
    });
  });
  