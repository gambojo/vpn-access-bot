fetch("/admin/stats")
  .then(res => res.json())
  .then(data => {
    const ctx = document.getElementById("chart").getContext("2d");
    new Chart(ctx, {
      type: "bar",
      data: {
        labels: data.labels,
        datasets: [{ label: "Подписки", data: data.counts }]
      }
    });
  });
