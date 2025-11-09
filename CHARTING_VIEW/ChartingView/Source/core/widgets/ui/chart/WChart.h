/*
  ==============================================================================

	WChart.h
	Created: 8 Nov 2025 12:45:58pm
	Author:  Jonathan

  ==============================================================================
*/

#pragma once
#include "../BaseComponent.h"
#include "WChartTransform.h"

class WChartAxis;
class WChartViewport;

class WChart : public BaseComponent {
public:
	WChart();
	~WChart();

	void paint(Graphics& g) override;
	void resized() override;

private:

	WChartScaleTransform _scaleT;
	UPtr<WChartAxis> _xAxis;
	UPtr<WChartAxis> _yAxis;
	UPtr<WChartViewport> _viewport;
};


