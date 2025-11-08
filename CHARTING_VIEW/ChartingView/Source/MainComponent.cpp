#include "MainComponent.h"
#include "core/WChartingView.h"


MainComponent::MainComponent()
	: _chartingView(new WChartingView())
{
	setSize(1200, 900);
	addAndMakeVisible(&*_chartingView);
}

MainComponent::~MainComponent()
{
}

void MainComponent::paint (juce::Graphics& g)
{
	g.fillAll (getLookAndFeel().findColour (juce::ResizableWindow::backgroundColourId));
}

void MainComponent::resized()
{
	_chartingView->setBounds(getLocalBounds());
}
