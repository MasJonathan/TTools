/*
  ==============================================================================

	WChartViewport.h
	Created: 8 Nov 2025 12:46:40pm
	Author:  Jonathan

  ==============================================================================
*/

#pragma once
#include "../BaseComponent.h"

class WChartViewport : public BaseComponent {
public:
	WChartViewport() {

	}

	void paint(Graphics& g) override {
		g.fillAll(Colours::blue);
	}

private:

};

