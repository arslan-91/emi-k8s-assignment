function loadHistory() {
  $.getJSON('/api/history', function (rows) {
    var $body = $('#historyBody').empty();
    rows.forEach(function (r) {
      var $tr = $('<tr>');
      $tr.append($('<td>').text(r.principal));
      $tr.append($('<td>').text(r.rate));
      $tr.append($('<td>').text(r.months));
      $tr.append($('<td>').text(r.emi));
      $tr.append($('<td>').text(r.servedBy));
      $tr.append($('<td>').text(new Date(r.createdAt).toLocaleString()));
      $body.append($tr);
    });
  });
}

$('#emiForm').on('submit', function (e) {
  e.preventDefault(); // postback nahi hoga, AJAX se submit
  var principal = parseFloat($('#principal').val());
  var rate = parseFloat($('#rate').val());
  var months = parseInt($('#months').val(), 10);

  // Client-side validation
  if (!(principal > 0) || !(rate > 0) || !(months > 0)) {
    $('#formError').text('Please enter positive numbers in all fields.');
    return;
  }
  $('#formError').text('');

  $.ajax({
    url: '/api/emi',
    method: 'POST',
    contentType: 'application/json',
    data: JSON.stringify({ principal: principal, rate: rate, months: months }),
    success: function (d) {
      $('#resEmi').text(d.emi.toFixed(2));
      $('#resTotal').text(d.totalPayment.toFixed(2));
      $('#resInterest').text(d.totalInterest.toFixed(2));
      $('#resPod').text(d.servedBy);
      $('#resIp').text(d.podIp);
      $('#resultPanel').removeClass('d-none');
      loadHistory();
    },
    error: function (xhr) {
      var msg = (xhr.responseJSON && xhr.responseJSON.error) || 'Request failed';
      $('#formError').text(msg);
    }
  });
});

loadHistory();
