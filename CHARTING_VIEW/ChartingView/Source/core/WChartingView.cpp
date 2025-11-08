/*
  ==============================================================================

	WChartingView.cpp
	Created: 8 Nov 2025 10:03:49am
	Author:  Jonathan

  ==============================================================================
*/

#include "WChartingView.h"
#include "widgets/ui/WLookAndFeel.h"
#include "widgets/ui/WColorSurface.h"

WChartingView::WChartingView() : _lnf(_initLnf()), _label("Toto") {
	auto* c1 = new WColorSurface(Colours::red.withSaturation(0.8f));
	auto* c2 = new WColorSurface(Colours::green.withSaturation(0.8f));
	auto* c3 = new WColorSurface(Colours::blue.withSaturation(0.8f));
	addAndMakeVisible(_label);
	ownAndMakeVisible(c1);
	ownAndMakeVisible(c2);
	ownAndMakeVisible(c3);
}

WChartingView::~WChartingView() {
	setLookAndFeel(nullptr);
}

void WChartingView::paint(Graphics& g) {
	g.fillAll(getLookAndFeel().findColour(juce::ResizableWindow::backgroundColourId));
}

WLookAndFeel* WChartingView::_initLnf() {
	auto* lnf = new WLookAndFeel();
	setLookAndFeel(lnf);
	return lnf;
}
