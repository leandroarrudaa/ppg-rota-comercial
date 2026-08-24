import { jsPDF } from "jspdf";
import autoTable from "jspdf-autotable";
import { recomendar, scriptContato } from "./recomendacao";
import { brl, dataHoraUtc, dataTexto, duracaoTexto, recenciaTexto, telefoneFmt } from "./format";

const M = 40;
const BAND_H = 56;
const NAVY_D = [13, 18, 52];   // #0d1234
const NAVY_L = [40, 52, 135];  // #283387
const YELLOW = [255, 207, 0];
const INK = [16, 22, 40];
const MUTED = [120, 126, 150];

const COR_FAIXA = {
  Ouro: [201, 162, 39],
  Prata: [142, 148, 155],
  Bronze: [180, 121, 63],
};

// ---- logo PPG (webp -> png via canvas, cacheado) ----
let logoPromise = null;
function getLogo() {
  if (logoPromise) return logoPromise;
  logoPromise = new Promise((resolve) => {
    const img = new Image();
    img.onload = () => {
      const cv = document.createElement("canvas");
      cv.width = img.naturalWidth;
      cv.height = img.naturalHeight;
      cv.getContext("2d").drawImage(img, 0, 0);
      resolve({ data: cv.toDataURL("image/png"), w: img.naturalWidth, h: img.naturalHeight });
    };
    img.onerror = () => resolve(null);
    img.src = "/ppg-logo.webp";
  });
  return logoPromise;
}

// faixa horizontal com degradê (azul-marinho escuro -> mais claro)
function gradiente(doc, x, y, w, h, c1, c2, steps = 80) {
  const sw = w / steps;
  for (let i = 0; i < steps; i++) {
    const t = i / (steps - 1);
    doc.setFillColor(
      Math.round(c1[0] + (c2[0] - c1[0]) * t),
      Math.round(c1[1] + (c2[1] - c1[1]) * t),
      Math.round(c1[2] + (c2[2] - c1[2]) * t)
    );
    doc.rect(x + i * sw, y, sw + 0.6, h, "F");
  }
}

// cabeçalho (letterhead) repetido em toda página
function cabecalho(doc, logo, titulo, subtitulo) {
  const W = doc.internal.pageSize.getWidth();
  gradiente(doc, 0, 0, W, BAND_H, NAVY_D, NAVY_L);
  // acento amarelo PPG na base
  doc.setFillColor(...YELLOW);
  doc.rect(0, BAND_H, W, 2.6, "F");

  // logo num chip branco
  if (logo) {
    const logoH = 26;
    const logoW = logoH * (logo.w / logo.h);
    const padX = 12;
    const chipW = logoW + padX * 2;
    const chipH = 40;
    const chipY = (BAND_H - chipH) / 2;
    doc.setFillColor(255, 255, 255);
    doc.roundedRect(M, chipY, chipW, chipH, 8, 8, "F");
    doc.addImage(logo.data, "PNG", M + padX, chipY + (chipH - logoH) / 2, logoW, logoH);
  }

  // título à direita, em branco
  doc.setTextColor(255, 255, 255);
  doc.setFont("helvetica", "bold");
  doc.setFontSize(15);
  doc.text(titulo, W - M, 26, { align: "right" });
  doc.setFont("helvetica", "normal");
  doc.setFontSize(8.5);
  doc.setTextColor(205, 211, 235);
  doc.text(subtitulo, W - M, 41, { align: "right" });
}

function rodape(doc, pagina) {
  const W = doc.internal.pageSize.getWidth();
  const H = doc.internal.pageSize.getHeight();
  doc.setDrawColor(225, 228, 240);
  doc.setLineWidth(0.8);
  doc.line(M, H - 30, W - M, H - 30);
  doc.setFont("helvetica", "bold");
  doc.setFontSize(7.5);
  doc.setTextColor(...NAVY_L);
  doc.text("PPG · Parafusos e Ferramentas", M, H - 19);
  doc.setFont("helvetica", "normal");
  doc.setTextColor(...MUTED);
  doc.text(`Página ${pagina}`, W - M, H - 19, { align: "right" });
}

// card branco com sombra simulada (offset cinza atrás)
function cardSombra(doc, x, y, w, h, r = 12) {
  doc.setFillColor(214, 218, 232);
  doc.roundedRect(x + 1.5, y + 3, w, h, r, r, "F");
  doc.setFillColor(255, 255, 255);
  doc.roundedRect(x, y, w, h, r, r, "F");
  doc.setDrawColor(232, 235, 245);
  doc.setLineWidth(0.7);
  doc.roundedRect(x, y, w, h, r, r, "S");
}

function estiloTabela(doc, logo, titulo, subtitulo, extra = {}) {
  return {
    margin: { left: M, right: M, top: BAND_H + 14, bottom: 42 },
    styles: { font: "helvetica", fontSize: 8, cellPadding: 6, valign: "top", lineColor: [238, 240, 247], lineWidth: 0.5, textColor: INK },
    headStyles: { fillColor: NAVY_L, textColor: [255, 255, 255], fontSize: 8.5, cellPadding: 7, lineWidth: 0 },
    alternateRowStyles: { fillColor: [248, 249, 252] },
    didDrawPage: (data) => {
      cabecalho(doc, logo, titulo, subtitulo);
      rodape(doc, data.pageNumber);
    },
    ...extra,
  };
}

// =================== PDF — ROTA DO DIA ===================
export async function gerarPdfDia({ diaNome, clientes, km, min, valor }) {
  const doc = new jsPDF({ orientation: "portrait", unit: "pt", format: "a4" });
  const W = doc.internal.pageSize.getWidth();
  const logo = await getLogo();
  const tempo = `${Math.floor(min / 60)}h${String(Math.round(min % 60)).padStart(2, "0")}`;

  // card de resumo (com sombra) — só na 1ª página
  const cardY = BAND_H + 16;
  const cardH = 56;
  cardSombra(doc, M, cardY, W - M * 2, cardH);
  const cols = [
    ["VISITAS", String(clientes.length)],
    ["DISTÂNCIA", `${km.toFixed(0)} km`],
    ["TEMPO EM ROTA", tempo],
    ["FATURAMENTO NA ROTA", brl(valor)],
  ];
  const colW = (W - M * 2) / 4;
  cols.forEach((c, i) => {
    const x = M + 16 + i * colW;
    if (i > 0) {
      doc.setDrawColor(235, 237, 245);
      doc.line(M + i * colW, cardY + 12, M + i * colW, cardY + cardH - 12);
    }
    doc.setFont("helvetica", "bold");
    doc.setFontSize(7);
    doc.setTextColor(...MUTED);
    doc.text(c[0], x, cardY + 21);
    doc.setFont("helvetica", "bold");
    doc.setFontSize(13);
    doc.setTextColor(...NAVY_L);
    doc.text(c[1], x, cardY + 39);
  });

  const body = clientes.map((c, i) => {
    const rec = recomendar(c);
    const endereco = [c.endereco, c.bairro].filter(Boolean).join(", ");
    const local = [c.cidade, c.uf].filter(Boolean).join("/");
    return [
      String(i + 1),
      `${c.nome}\n${c.faixa}${c.emRisco ? " · EM RISCO" : ""}`,
      `${endereco}\n${local}`,
      `${recenciaTexto(c.recencia)}${c.cadencia ? `\ncada ${c.cadencia}d` : ""}`,
      `${rec.titulo}\n${rec.texto}`,
    ];
  });

  autoTable(doc, estiloTabela(doc, logo, `Rota de ${diaNome}`, "Plano de visitas", {
    startY: cardY + cardH + 18,
    head: [["#", "Empresa", "Endereço", "Última compra", "Ação recomendada"]],
    body,
    columnStyles: {
      0: { cellWidth: 24, halign: "center", fontStyle: "bold", fontSize: 10 },
      1: { cellWidth: 118, fontStyle: "bold" },
      2: { cellWidth: 118 },
      3: { cellWidth: 68 },
      4: { cellWidth: 183 },
    },
    didParseCell: (data) => {
      if (data.section === "body" && data.column.index === 0) {
        data.cell.styles.textColor = COR_FAIXA[clientes[data.row.index].faixa] || INK;
      }
    },
  }));

  doc.save(`rota-${diaNome.toLowerCase()}.pdf`);
}

// =================== PDF — LISTA DE CONTATOS ===================
export async function gerarPdfContato({ diaNome, clientes }) {
  const doc = new jsPDF({ orientation: "portrait", unit: "pt", format: "a4" });
  const W = doc.internal.pageSize.getWidth();
  const logo = await getLogo();

  const comTel = clientes.filter((c) => c.telefone).length;
  const potencial = clientes.reduce((s, c) => s + (c.fat || 0), 0);

  const cardY = BAND_H + 16;
  const cardH = 56;
  cardSombra(doc, M, cardY, W - M * 2, cardH);
  const cols = [
    ["CONTATOS", String(clientes.length)],
    ["COM TELEFONE", `${comTel}/${clientes.length}`],
    ["POTENCIAL DE REATIVAÇÃO", brl(potencial)],
  ];
  const colW = (W - M * 2) / 3;
  cols.forEach((c, i) => {
    const x = M + 16 + i * colW;
    if (i > 0) {
      doc.setDrawColor(235, 237, 245);
      doc.line(M + i * colW, cardY + 12, M + i * colW, cardY + cardH - 12);
    }
    doc.setFont("helvetica", "bold");
    doc.setFontSize(7);
    doc.setTextColor(...MUTED);
    doc.text(c[0], x, cardY + 21);
    doc.setFont("helvetica", "bold");
    doc.setFontSize(13);
    doc.setTextColor(...NAVY_L);
    doc.text(c[1], x, cardY + 39);
  });

  const body = clientes.map((c, i) => {
    const s = scriptContato(c);
    return [
      String(i + 1),
      `${c.nome}\n${c.faixa} · ${c.cidade || ""}/${c.uf || ""}`,
      telefoneFmt(c.telefone) || "—",
      `${recenciaTexto(c.recencia)}\nR$ ${(c.fat || 0).toLocaleString("pt-BR", { maximumFractionDigits: 0 })}`,
      `[${s.prioridade}] ${s.objetivo}\n${s.script}`,
    ];
  });

  autoTable(doc, estiloTabela(doc, logo, `Contatos de ${diaNome}`, "Reativação de clientes", {
    startY: cardY + cardH + 18,
    head: [["#", "Empresa", "Telefone", "Sem comprar", "Abordagem"]],
    body,
    columnStyles: {
      0: { cellWidth: 24, halign: "center", fontStyle: "bold", fontSize: 10 },
      1: { cellWidth: 128, fontStyle: "bold" },
      2: { cellWidth: 82 },
      3: { cellWidth: 72 },
      4: { cellWidth: 203 },
    },
    didParseCell: (data) => {
      if (data.section === "body" && data.column.index === 0) {
        data.cell.styles.textColor = COR_FAIXA[clientes[data.row.index].faixa] || INK;
      }
    },
  }));

  doc.save(`contatos-${diaNome.toLowerCase()}.pdf`);
}

// =================== PDF — RELATÓRIO DE VISITAS ===================
export async function gerarPdfRelatorio({ tituloPeriodo, resumo, visitas }) {
  const doc = new jsPDF({ orientation: "portrait", unit: "pt", format: "a4" });
  const W = doc.internal.pageSize.getWidth();
  const logo = await getLogo();

  const cardY = BAND_H + 16;
  const cardH = 56;
  cardSombra(doc, M, cardY, W - M * 2, cardH);
  const cols = [
    ["VISITAS", String(resumo.totalVisitas)],
    ["CLIENTES ÚNICOS", String(resumo.clientesUnicos)],
    ["DURAÇÃO MÉDIA", resumo.duracaoMediaMin != null ? duracaoTexto(resumo.duracaoMediaMin) : "—"],
    ["RETORNOS AGENDADOS", String(resumo.retornosAgendados)],
  ];
  const colW = (W - M * 2) / 4;
  cols.forEach((c, i) => {
    const x = M + 16 + i * colW;
    if (i > 0) {
      doc.setDrawColor(235, 237, 245);
      doc.line(M + i * colW, cardY + 12, M + i * colW, cardY + cardH - 12);
    }
    doc.setFont("helvetica", "bold");
    doc.setFontSize(7);
    doc.setTextColor(...MUTED);
    doc.text(c[0], x, cardY + 21);
    doc.setFont("helvetica", "bold");
    doc.setFontSize(13);
    doc.setTextColor(...NAVY_L);
    doc.text(c[1], x, cardY + 39);
  });

  const body = visitas.map((v, i) => {
    const dh = dataHoraUtc(v.inicio);
    const dataFmt = dh.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
    const horaFmt = dh.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
    const promessasTxt = v.promessas.length ? `\nPromessas: ${v.promessas.map((p) => p.texto).join("; ")}` : "";
    return [
      String(i + 1),
      `${dataFmt}\n${horaFmt}`,
      `${v.clienteNome}\n${v.clienteCidade || ""} · ${v.vendedorNome}`,
      duracaoTexto(v.duracaoMin),
      v.retornoData ? dataTexto(v.retornoData) : "—",
      `${v.observacao || ""}${promessasTxt}`,
    ];
  });

  autoTable(doc, estiloTabela(doc, logo, "Relatório de visitas", tituloPeriodo, {
    startY: cardY + cardH + 18,
    head: [["#", "Data", "Cliente", "Duração", "Retorno", "Observação"]],
    body,
    columnStyles: {
      0: { cellWidth: 22, halign: "center", fontStyle: "bold", fontSize: 9 },
      1: { cellWidth: 56 },
      2: { cellWidth: 118, fontStyle: "bold" },
      3: { cellWidth: 48 },
      4: { cellWidth: 58 },
      5: { cellWidth: 183 },
    },
  }));

  doc.save("relatorio-visitas.pdf");
}
