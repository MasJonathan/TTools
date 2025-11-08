/*
  ==============================================================================

    WChartScaleData.h
    Created: 8 Nov 2025 1:38:15pm
    Author:  Jonathan

  ==============================================================================
*/

#pragma once
#include "JuceHeader.h"

/*
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

*/


class WChartScaleData {
public:
	enum class XAxisDirection {
		left_to_right,
		right_to_left
	};
	enum class YAxisDirection {
		bot_to_top,
		top_to_bot
	};
	struct AxisTransform {
		float worldStart;
		float worldEnd;
		float viewportStart;
		float viewportEnd;
	};
	struct AxisMapTransform {
		AxisTransform pixelT;
		AxisTransform unitT;
	};
	struct XAxis {
		AxisMapTransform axisT;
		XAxisDirection direction = XAxisDirection::left_to_right;
	};
	struct YAxis {
		AxisMapTransform axisT;
		YAxisDirection direction = YAxisDirection::bot_to_top;
	};


	enum class SamplingMode
	{
		None,        // tous les points
		Auto,        // adapte en fonction des pixels
		FixedDensity // max n points par viewport
	};
	struct SamplingConfig
	{
		SamplingMode mode = SamplingMode::Auto;
		float maxPointsPerPixel = 1.0f;  // densité max (Auto/Fixed)
		int   minPointsPerSegment = 1;     // sécurité

		// éventuellement : type de décimation
		// enum class Strategy { MinMax, FirstLast, OHLCCompress, ... };
		// Strategy strategy = Strategy::MinMax;
	};


	// conversion of units and viewport size
	XAxis xAxis;
	YAxis yAxis;

	// sampling : how much data density is displayed in this viewport
	// max map density is one data by pixel
	bool samplingAuto = true; // try to display maximum values possible
};





