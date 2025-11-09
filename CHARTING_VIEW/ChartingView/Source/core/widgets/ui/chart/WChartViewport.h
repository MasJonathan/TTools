/*
  ==============================================================================

	WChartViewport.h
	Created: 8 Nov 2025 12:46:40pm
	Author:  Jonathan

  ==============================================================================
*/

#pragma once
#include "../BaseComponent.h"

class WChartScaleTransform;


/*
Il faut pouvoir feed une chart avec des samples, voir les resampler

Il faut d'abord la logique de stream :
	- on précise la fenetre temporelle
	- on calcul combien de valeurs peuvent etres affichées dans cette fenetre
	- on doit get ces valeurs seulement
	- on les plots sur le chart

Comment cela fonctionnerait pour
	- des dates ? -> label = rect to plot
	- des prix ?  -> label = rect to plot
	- des lines markers ? lines to plot = rect to plot
	- des klines ?	candlesticks = rect to plot

Il faudrait surement un concept de layouts dédié aux charts
	un truc qui prends la taille min des objets et dit combien max on peut placer
		si on a pas assez de place on fait quoi ?
			on en met moins ?
			ou on autorise pas le zoom in out

*/

class WChartViewport : public BaseComponent {
public:
	WChartViewport(WChartScaleTransform& scaleT);

	void paint(Graphics& g) override;

private:
	WChartScaleTransform& _scaleT;
};

