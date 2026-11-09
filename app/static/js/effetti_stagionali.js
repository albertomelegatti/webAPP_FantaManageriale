// Foglie dal 15 ottobre al 30 novembre, neve dal 1 dicembre al 6 gennaio.
const oggi = new Date();
const mese = oggi.getMonth();
const giorno = oggi.getDate();

if ((mese === 9 && giorno >= 15) || mese === 10) {
    const { FallingLeaves } = await import('https://cdn.jsdelivr.net/npm/falling-leaves@0.1.0/+esm');
    new FallingLeaves({ count: 30, shapes: ['maple', 'oak', 'ginkgo', 'birch', 'oval'] });
} else if (mese === 11 || (mese === 0 && giorno <= 6)) {
    const { Snowfall } = await import('https://cdn.jsdelivr.net/npm/falling-snow@1.0.0/+esm');
    new Snowfall({ count: 60 });
}
