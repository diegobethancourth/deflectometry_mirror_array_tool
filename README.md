Interactive Mirror Array Calculator

📌 About
An interactive web-based calculator was developed to support the array sizing analysis for deflectometry setup. The tool applies six governing equations (pixel pitch, fringe pitch, array width/height, fringes across array, screen FOV and Camera AOV simultaneously for any selected layout. Controls allow real-time adjustment of mirror gap, screen distance, pixels per fringe, sensor format and focal lenght. 
A live mathematics panel displays each equation with its current numerical result, and a comparison table ranks all six candidate configurations. The tool is accessible through my git hub.

🚀 Formulas

Expression	Physical Meaning
p = W / Nₓ	Pixel pitch: screen width ÷ horizontal pixels
P_f = n × p	Fringe pitch: pixels per fringe × pixel pitch
L = n_cols × a + (n_cols−1) × g	Array width: mirrors + gaps
N_f = L / P_f	Fringes across array: must be ≥ 40 (≥ 60 ideal)
θ = 2·arctan(Ws/2d)	Screen angular FOV: array must fit inside

Authors: 
Diego Bethancourth | (Quote Credits)
