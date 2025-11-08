
pouvoir feed les charts 
	avec des fichiers
	avec des listes de données
	avec des fonctions dynamiques

animationCurves
	lineaire
	curves de beziers avecs keyframes

chart
	Les charts gèrent l'échelle, et le pool d'objets à afficher
	L'échelle est gérée avec 
		un viewport rect et son pivot en pixel
		un viewport rect et son pivot mais dans l'unité de référence
		un content rect (contenu total) en unité de référence
		une option pour gérer la conversion x ou y de façon linéaire ou logarithmique
		une option pour inverser l'axe x ou y
		un zoom scale en x ou y
		des presets de zoom scales (utile pour changer les timeframes)
		une option pour snap sur les zoom scales quand on zoom

		une fonction pour zoom sur le max scale (et voir tout le contenu)
		(échantillonnage à seulement ce qui est visible au pixel level)
		
	les charts display des objets en unité de référence

	addCurve()
		fill
		dashed
		dot
		area
	addShape()
		dot
		circle
			hollow 
			fill
		triangle
			hollow 
			fill
		rect
			hollow
			fill
		path
			hollow
			fill
	addHistogram()
		hollow
		fill

chartmanager
	pouvoir cumuler des charts

guimanager
	pouvoir gérer des objets (panels, editors, ui widgets), leurs layouts

Comment communiquer avec python ?
	pipes ?








